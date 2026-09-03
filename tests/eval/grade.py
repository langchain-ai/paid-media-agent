"""Grade a results file: numeric checks from the fixtures, then a table for human judgment.

Usage: grade.py <results.jsonl>
"""

from __future__ import annotations

import json
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

from paid_media_agent.domain.common import PIPEBOARD_PLATFORMS
from paid_media_agent.tools.fixtures import load_fixture_dataset

LAST_WEEK = (date(2026, 8, 24), date(2026, 8, 30))
PRIOR_WEEK = (date(2026, 8, 17), date(2026, 8, 23))
AUGUST = (date(2026, 8, 1), date(2026, 8, 31))


def window_totals(platform: str, window: tuple[date, date]) -> dict[str, str | None]:
    """Spend, conversions, and CPA for one platform over one window, from the fixture rows."""
    rows = [
        r
        for r in load_fixture_dataset(next(p for p in PIPEBOARD_PLATFORMS if p.value == platform))[
            "daily"
        ]
        if window[0] <= date.fromisoformat(str(r["date"])) <= window[1]
    ]
    spend = sum(Decimal(str(r["spend"])) for r in rows)
    conversions = sum(Decimal(str(r["conversions"])) for r in rows)
    cpa = (spend / conversions).quantize(Decimal("0.01")) if conversions else None
    return {
        "spend": str(spend),
        "conversions": str(conversions),
        "cpa": None if cpa is None else str(cpa),
    }


def expected_figures(question_id: str) -> list[str]:
    """Figures the answer must quote, when the question has a deterministic one."""
    if question_id == "q01_wow_spend":
        return [
            window_totals(p.value, w)["spend"]
            for p in PIPEBOARD_PLATFORMS
            for w in (LAST_WEEK, PRIOR_WEEK)
        ]
    if question_id == "q02_cpa_movers":
        # With data complete on a Thursday, "last week" is legitimately either the calendar week or
        # the seven days ending on the last complete day; the check below accepts either pair.
        return []
    if question_id == "q05_cross_total":
        return [window_totals(p.value, AUGUST)["spend"] for p in PIPEBOARD_PLATFORMS]
    return []


WEEK_PAIRS = (
    (LAST_WEEK, PRIOR_WEEK),
    ((date(2026, 8, 22), date(2026, 8, 28)), (date(2026, 8, 15), date(2026, 8, 21))),
)


def cpa_windows_present(answer: str) -> bool:
    """True when the answer quotes Google spend for one accepted pair of comparison windows."""
    return any(
        all(window_totals("google_ads", w)["spend"] in answer for w in pair) for pair in WEEK_PAIRS
    )


def main(path: str) -> int:
    questions = {
        q["id"]: q for q in json.loads(Path(__file__).with_name("questions.json").read_text())
    }
    failures = 0
    for line in Path(path).read_text().splitlines():
        record = json.loads(line)
        answer = (record.get("answer") or "").replace(",", "")
        missing = [f for f in expected_figures(record["id"]) if f not in answer]
        if record["id"] == "q02_cpa_movers" and not cpa_windows_present(answer):
            missing.append("google spend for an accepted window pair")
        verdict = "numbers ok" if not missing else f"missing {missing}"
        if missing or record.get("error"):
            failures += 1
        print(f"{record['id']:18} {record.get('seconds', 0):7.1f}s {verdict}")
        print(f"  tools: {record.get('tools')}")
        print(f"  expect: {questions[record['id']]['expect']}")
        if record.get("error"):
            print(f"  error: {record['error']}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
