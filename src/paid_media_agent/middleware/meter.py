"""The cost meter: what each model call cost, summed per conversation, lead and helpers together.

- `load_prices()`: list prices per million tokens from `prices.toml` beside this file. Every
  figure is an estimate; a model the table does not list is counted as unpriced, never guessed.
- `cost_of(usage, price)`: one call's cost from LangChain's `usage_metadata`, with cache reads and
  writes priced apart (a cache write costs more than a read, so the split matters). A message with
  no usage (a scripted model, a retry's error reply) cost nothing and is not counted.
- `Meter`: a ledger in the LangGraph store, namespaced by the conversation's thread. Each run
  writes only its own entry, so a lead and its background helpers never race on one key. On
  Managed Deep Agents a helper's `runtime.thread` is its lead's thread, so a helper's spend lands
  in its lead's conversation; elsewhere the thread is the run's own. Without a store (the CLI,
  the self-hosted server) the ledger is an in-memory store owned by this meter.
- `MeterMiddleware`: records every model call of the agent it is attached to.

The meter also keeps the conversation's current *job*: the latest request from a person, with what
the conversation had cost when it arrived. The footer (`middleware/footer.py`) reports the job.
"""

from __future__ import annotations

import logging
import re
import time
import tomllib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import cache
from importlib import resources
from typing import Any

from langchain.agents.middleware import AgentMiddleware, AgentState
from langchain_core.messages import AIMessage
from langgraph.config import get_config
from langgraph.store.base import BaseStore
from langgraph.store.memory import InMemoryStore

_LOGGER = logging.getLogger(__name__)

NAMESPACE = ("paid_media_agent", "meter")
JOB_KEY = "job"
LEAD_KEY = "lead"
_DATED = re.compile(r"-(?:\d{8}|\d{4}-\d{2}-\d{2})$")


@dataclass(frozen=True)
class Price:
    """USD per million tokens. `long_context` applies past `long_context_above` prompt tokens."""

    input: float
    output: float
    cache_read: float
    cache_write_5m: float
    cache_write_1h: float
    long_context: Price | None = None
    long_context_above: int | None = None

    def for_prompt(self, prompt_tokens: int) -> Price:
        if self.long_context is not None and self.long_context_above is not None:
            if prompt_tokens > self.long_context_above:
                return self.long_context
        return self


def _price(row: Mapping[str, Any]) -> Price:
    write_5m = float(row.get("cache_write_5m", row["input"]))
    long = row.get("long_context")
    return Price(
        input=float(row["input"]),
        output=float(row["output"]),
        cache_read=float(row.get("cache_read", row["input"])),
        cache_write_5m=write_5m,
        cache_write_1h=float(row.get("cache_write_1h", write_5m)),
        long_context=_price(long) if isinstance(long, Mapping) else None,
        long_context_above=int(long["above_input_tokens"]) if isinstance(long, Mapping) else None,
    )


@cache
def load_prices() -> Mapping[str, Price]:
    """Every model in `prices.toml`, keyed by its bare name and each of its `aliases`."""
    text = resources.files("paid_media_agent.middleware").joinpath("prices.toml").read_text("utf-8")
    prices: dict[str, Price] = {}
    for provider in tomllib.loads(text).values():
        for name, row in (provider.get("models") or {}).items():
            price = _price(row)
            for key in (name, *row.get("aliases", ())):
                prices[key] = price
    return prices


def price_for(model: str, prices: Mapping[str, Price] | None = None) -> Price | None:
    """The price of `model`, or None if unlisted. Only a `provider:` prefix and a dated snapshot
    suffix are ignored: a variant such as `-mini` or `-pro` is another model with other prices."""
    table = load_prices() if prices is None else prices
    return table.get(_DATED.sub("", model.rpartition(":")[2].strip().lower()))


def _count(details: Mapping[str, Any], key: str) -> int:
    value = details.get(key)
    return int(value) if isinstance(value, int | float) and value > 0 else 0


def cost_of(usage: Mapping[str, Any], price: Price) -> float:
    """One call's cost in USD from LangChain `usage_metadata`."""
    prompt = _count(usage, "input_tokens")
    details = usage.get("input_token_details")
    details = details if isinstance(details, Mapping) else {}
    read = _count(details, "cache_read")
    written = _count(details, "cache_creation")
    hour = _count(details, "ephemeral_1h_input_tokens")
    rate = price.for_prompt(prompt)
    uncached = max(prompt - read - written, 0)
    usd = (
        uncached * rate.input
        + read * rate.cache_read
        + max(written - hour, 0) * rate.cache_write_5m
        + min(hour, written) * rate.cache_write_1h
        + _count(usage, "output_tokens") * rate.output
    )
    return usd / 1_000_000


@dataclass(frozen=True)
class Totals:
    usd: float = 0.0
    calls: int = 0
    unpriced: int = 0


@dataclass(frozen=True)
class Job:
    """A person's latest request: when it arrived and what the conversation had cost by then."""

    started: float
    base: Totals


def _configurable() -> Mapping[str, Any]:
    try:
        config = get_config()
    except RuntimeError:
        return {}
    found = config.get("configurable")
    return found if isinstance(found, Mapping) else {}


def run_thread() -> str:
    """This run's own LangGraph thread."""
    return str(_configurable().get("thread_id") or "")


def conversation_thread(runtime: Any = None) -> str:
    """The conversation a run belongs to: on MDA an async helper's is its lead's."""
    thread = getattr(getattr(runtime, "thread", None), "id", None)
    return str(thread) if thread else run_thread()


def _totals(value: Mapping[str, Any]) -> Totals:
    return Totals(
        usd=float(value.get("usd") or 0.0),
        calls=int(value.get("calls") or 0),
        unpriced=int(value.get("unpriced") or 0),
    )


class Meter:
    """The conversation ledger (module doc)."""

    def __init__(
        self,
        *,
        default_model: str = "",
        prices: Mapping[str, Price] | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._default_model = default_model
        self._prices = load_prices() if prices is None else prices
        self._fallback = InMemoryStore()
        self.clock = clock

    def store(self, runtime: Any) -> BaseStore:
        found = getattr(runtime, "store", None)
        return found if isinstance(found, BaseStore) else self._fallback

    def _where(self, runtime: Any) -> tuple[tuple[str, ...], str] | None:
        conversation = conversation_thread(runtime)
        if not conversation:
            return None
        own = run_thread()
        return (*NAMESPACE, conversation), LEAD_KEY if own in ("", conversation) else own

    def _price(self, message: AIMessage) -> tuple[float, bool] | None:
        usage = message.usage_metadata
        if not usage:
            return None
        metadata = message.response_metadata or {}
        model = str(metadata.get("model_name") or metadata.get("model") or self._default_model)
        price = price_for(model, self._prices)
        if price is None:
            return 0.0, False
        return cost_of(dict(usage), price), True

    async def record(self, runtime: Any, message: AIMessage) -> None:
        where, cost = self._where(runtime), self._price(message)
        if where is None or cost is None:
            return
        namespace, key = where
        usd, priced = cost
        store = self.store(runtime)
        item = await store.aget(namespace, key)
        await store.aput(namespace, key, self._add(item.value if item else {}, usd, priced))

    def record_sync(self, runtime: Any, message: AIMessage) -> None:
        where, cost = self._where(runtime), self._price(message)
        if where is None or cost is None:
            return
        namespace, key = where
        usd, priced = cost
        store = self.store(runtime)
        item = store.get(namespace, key)
        store.put(namespace, key, self._add(item.value if item else {}, usd, priced))

    @staticmethod
    def _add(value: Mapping[str, Any], usd: float, priced: bool) -> dict[str, Any]:
        totals = _totals(value)
        return {
            "usd": totals.usd + usd,
            "calls": totals.calls + 1,
            "unpriced": totals.unpriced + (0 if priced else 1),
        }

    async def totals(self, runtime: Any) -> Totals:
        """The conversation's spend so far, lead and helpers together."""
        conversation = conversation_thread(runtime)
        if not conversation:
            return Totals()
        items = await self.store(runtime).asearch((*NAMESPACE, conversation), limit=200)
        usd, calls, unpriced = 0.0, 0, 0
        for item in items:
            if item.key == JOB_KEY:
                continue
            found = _totals(item.value)
            usd, calls, unpriced = usd + found.usd, calls + found.calls, unpriced + found.unpriced
        return Totals(usd, calls, unpriced)

    async def start_job(self, runtime: Any) -> None:
        conversation = conversation_thread(runtime)
        if not conversation:
            return
        base = await self.totals(runtime)
        await self.store(runtime).aput(
            (*NAMESPACE, conversation),
            JOB_KEY,
            {
                "started": self.clock(),
                "usd": base.usd,
                "calls": base.calls,
                "unpriced": base.unpriced,
            },
        )

    async def job(self, runtime: Any) -> Job | None:
        conversation = conversation_thread(runtime)
        if not conversation:
            return None
        item = await self.store(runtime).aget((*NAMESPACE, conversation), JOB_KEY)
        if item is None:
            return None
        return Job(started=float(item.value.get("started") or 0.0), base=_totals(item.value))


class MeterMiddleware(AgentMiddleware[AgentState[Any], Any, Any]):
    """Record each model call's cost. A failed write costs the estimate, never the run."""

    name = "PaidMediaMeter"

    def __init__(self, meter: Meter) -> None:
        super().__init__()
        self._meter = meter

    @staticmethod
    def _latest(state: AgentState[Any]) -> AIMessage | None:
        messages = state.get("messages") or []
        last = messages[-1] if messages else None
        return last if isinstance(last, AIMessage) else None

    def after_model(self, state: AgentState[Any], runtime: Any) -> dict[str, Any] | None:
        message = self._latest(state)
        if message is not None:
            try:
                self._meter.record_sync(runtime, message)
            except Exception as error:  # the estimate is presentation only
                _LOGGER.warning("[meter] call not recorded: %s", type(error).__name__)
        return None

    async def aafter_model(self, state: AgentState[Any], runtime: Any) -> dict[str, Any] | None:
        message = self._latest(state)
        if message is not None:
            try:
                await self._meter.record(runtime, message)
            except Exception as error:  # the estimate is presentation only
                _LOGGER.warning("[meter] call not recorded: %s", type(error).__name__)
        return None
