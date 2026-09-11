"""The organization's own context: a short profile and sources the agent reads before analysis.

It lives in `docs/org/` (ignored by git, mounted at `/docs/org` in every runtime). Two entry
points write it, the coding agent through the onboarding skill and `paid-media-agent org`,
and both render the same pages from one profile, so the model never sees a schema.
"""

from __future__ import annotations

import ipaddress
import json
import re
import shutil
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import NamedTuple
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, ConfigDict

from paid_media_agent.domain.common import JsonValue

ORG_DIR = Path("docs/org")
PROFILE_FILE = "profile.json"
SOURCES_DIR = "sources"
SOURCES_PAGE = "sources.md"
PAGES = ("goals.md", "conventions.md", SOURCES_PAGE)
TEXT_SUFFIXES = {".md", ".txt", ".csv", ".json", ".html", ".htm"}
MAX_SOURCE_BYTES = 1_000_000
"""Stored text per source; also the file upload cap."""
MAX_DOWNLOAD_BYTES = 5_000_000
"""Raw page size we are willing to fetch; HTML shrinks a lot once scripts and markup are gone."""
FETCH_TIMEOUT_SECONDS = 20.0


class OrgProfile(BaseModel):
    """Plain-language answers. Empty strings mean "not answered yet"."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    business: str = ""
    primary_conversion: str = ""
    targets: str = ""
    monthly_budget: str = ""
    markets: str = ""
    seasonality: str = ""
    naming: str = ""
    approvers: str = ""
    notes: str = ""
    updated_at: datetime | None = None

    def answered(self) -> int:
        return sum(1 for q in QUESTIONS if getattr(self, q.field).strip())


class OrgQuestion(NamedTuple):
    field: str
    question: str
    why: str
    example: str


QUESTIONS: tuple[OrgQuestion, ...] = (
    OrgQuestion(
        "business",
        "What do you sell, and who buys it?",
        "Frames every recommendation; B2B pipeline and e-commerce checkout are judged differently.",
        "Project-management software for mid-size engineering teams; buyers are engineering managers.",
    ),
    OrgQuestion(
        "primary_conversion",
        "Which conversion counts as success on each platform?",
        "Platforms report several events; the agent must know which one is the outcome.",
        "Google: demo request (offline import). Meta: trial signup. LinkedIn: lead form.",
    ),
    OrgQuestion(
        "targets",
        "Do you have a target cost per conversion or return on ad spend? If not, say so.",
        "With no target the agent stays directional and never invents a benchmark.",
        "Blended CPA under 120 USD; brand search under 20 USD; no ROAS target yet.",
    ),
    OrgQuestion(
        "monthly_budget",
        "Roughly how much do you spend per month, and in which currency?",
        "Pacing and the size of a proposed change are read against the whole budget.",
        "About 60,000 USD across platforms; Google is two thirds.",
    ),
    OrgQuestion(
        "markets",
        "Which markets do you run in, and in what timezone do you read reports?",
        "Windows, currency, and day boundaries follow this.",
        "US and UK; reports in America/New_York; accounts bill in USD.",
    ),
    OrgQuestion(
        "seasonality",
        "Any seasonality, launches, or dates the agent should not misread as anomalies?",
        "Stops a planned spike from being flagged as a problem.",
        "Q4 push from mid-October; conference weeks double LinkedIn spend.",
    ),
    OrgQuestion(
        "naming",
        "How are campaigns named, and what marks brand versus non-brand or prospecting versus retargeting?",
        "Lets the agent group campaigns the way you do.",
        "Prefix by funnel: BR- brand, NB- non-brand, RT- retargeting; market code at the end.",
    ),
    OrgQuestion(
        "approvers",
        "Who may approve budget or status changes?",
        "Approval identity is host-owned; this is the human list the agent names.",
        "The paid media lead and the head of growth.",
    ),
)


def org_dir(root: Path) -> Path:
    return root / ORG_DIR


def load_profile(root: Path) -> OrgProfile:
    path = org_dir(root) / PROFILE_FILE
    if not path.exists():
        return OrgProfile()
    return OrgProfile.model_validate(json.loads(path.read_text(encoding="utf-8")))


def save_profile(root: Path, profile: OrgProfile) -> list[Path]:
    """Write the profile and render the pages the model reads. Returns the written paths."""
    directory = org_dir(root)
    directory.mkdir(parents=True, exist_ok=True)
    stamped = profile.model_copy(update={"updated_at": datetime.now(UTC)})
    written = [directory / PROFILE_FILE, directory / "goals.md", directory / "conventions.md"]
    written[0].write_text(stamped.model_dump_json(indent=2), encoding="utf-8")
    written[1].write_text(render_goals(stamped), encoding="utf-8")
    written[2].write_text(render_conventions(stamped), encoding="utf-8")
    sources = directory / SOURCES_PAGE
    if not sources.exists():
        sources.write_text(
            "# Sources\n\nLinks and files the organization shared. Newest last.\n", encoding="utf-8"
        )
        written.append(sources)
    return written


def _section(title: str, value: str, fallback: str) -> str:
    return f"## {title}\n\n{value.strip() or fallback}\n\n"


def render_goals(profile: OrgProfile) -> str:
    return (
        "# Goals and economics for this organization\n\n"
        "Answers given during onboarding. They override the generic doctrine in\n"
        '`/skills/paid-media-wiki` wherever the two differ. Say "not provided" when a field is empty;\n'
        "never fill it with an industry guess.\n\n"
        + _section("What we sell and to whom", profile.business, "Not provided.")
        + _section(
            "The conversion that counts",
            profile.primary_conversion,
            "Not provided; treat platform-reported conversions as directional.",
        )
        + _section(
            "Targets",
            profile.targets,
            "No target configured; stay directional and compare against the account's own history.",
        )
        + _section("Monthly budget", profile.monthly_budget, "Not provided.")
        + _section(
            "Markets, currency, timezone",
            profile.markets,
            "Not provided; use the account settings from list_accounts.",
        )
        + _section("Seasonality and planned spikes", profile.seasonality, "None recorded.")
        + _section("Notes", profile.notes, "None.")
    )


def render_conventions(profile: OrgProfile) -> str:
    return (
        "# Conventions for this organization\n\n"
        + _section(
            "Campaign naming",
            profile.naming,
            "Not provided; group by platform-reported names only.",
        )
        + _section(
            "Who approves changes",
            profile.approvers,
            "Not provided; the host approval policy still decides who can approve.",
        )
    )


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:60] or "source"


class _TextExtractor(HTMLParser):
    """Keep visible text, drop scripts and styles."""

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag in ("script", "style", "noscript"):
            self._skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "noscript") and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip and data.strip():
            self.parts.append(data.strip())


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    return "\n".join(parser.parts)


class SourceError(Exception):
    pass


def _check_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise SourceError("only https links are accepted")
    host = parsed.hostname
    if host in ("localhost",) or host.endswith((".local", ".internal")):
        raise SourceError("private hosts are not fetched")
    try:
        if not ipaddress.ip_address(host).is_global:
            raise SourceError("private addresses are not fetched")
    except ValueError:
        pass  # a hostname, not a literal address


def fetch_text(url: str) -> str:
    """Fetch a public https page and return its visible text, bounded in size and time."""
    _check_url(url)
    with httpx.Client(timeout=FETCH_TIMEOUT_SECONDS, follow_redirects=True) as client:
        response = client.get(url, headers={"User-Agent": "paid-media-agent/0.1 (org onboarding)"})
    if response.status_code >= 400:
        raise SourceError(f"the link answered {response.status_code}")
    if len(response.content) > MAX_DOWNLOAD_BYTES:
        raise SourceError("the page is larger than 5 MB; share a smaller page or a file")
    content_type = response.headers.get("content-type", "")
    text = (html_to_text(response.text) if "html" in content_type else response.text).strip()
    if len(text.encode("utf-8")) > MAX_SOURCE_BYTES:
        raise SourceError("the page has more than 1 MB of text; share a smaller page or a file")
    return text


def _append_source(root: Path, title: str, stored: Path, note: str) -> None:
    page = org_dir(root) / SOURCES_PAGE
    if not page.exists():
        save_profile(root, load_profile(root))
    line = f"- [{title}](/docs/org/{SOURCES_DIR}/{stored.name})"
    if note.strip():
        line += f": {note.strip()}"
    with page.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def add_link(root: Path, url: str, note: str = "", *, fetch: object = None) -> Path:
    """Store the text of a public page under sources/ and list it on the sources page."""
    text = (fetch or fetch_text)(url)  # type: ignore[operator]
    if not text:
        raise SourceError("the page had no readable text")
    directory = org_dir(root) / SOURCES_DIR
    directory.mkdir(parents=True, exist_ok=True)
    title = urlparse(url).netloc + urlparse(url).path.rstrip("/")
    stored = directory / f"{slugify(title)}.md"
    stored.write_text(f"# {title}\n\nSource: {url}\n\n{text}\n", encoding="utf-8")
    _append_source(root, title, stored, note)
    return stored


def add_file(root: Path, path: Path, note: str = "") -> Path:
    """Copy a text-like file the organization shared into sources/ and list it."""
    if path.suffix.lower() not in TEXT_SUFFIXES:
        raise SourceError(
            f"{path.suffix or 'that type'} is not a text file; share .md, .txt, .csv, .json, or .html"
        )
    if not path.is_file():
        raise SourceError("file not found")
    if path.stat().st_size > MAX_SOURCE_BYTES:
        raise SourceError("the file is larger than 1 MB")
    directory = org_dir(root) / SOURCES_DIR
    directory.mkdir(parents=True, exist_ok=True)
    stored = directory / f"{slugify(path.stem)}{path.suffix.lower()}"
    shutil.copyfile(path, stored)
    _append_source(root, path.name, stored, note)
    return stored


def org_summary(root: Path) -> dict[str, JsonValue]:
    """What the console and doctor show: how much of the profile exists and what was shared."""
    profile = load_profile(root)
    sources = org_dir(root) / SOURCES_DIR
    return {
        "configured": profile.answered() > 0,
        "answered": profile.answered(),
        "questions": len(QUESTIONS),
        "sources": sorted(p.name for p in sources.iterdir()) if sources.exists() else [],
        "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
    }


def questions_json() -> list[JsonValue]:
    return [dict(q._asdict()) for q in QUESTIONS]


__all__ = [
    "ORG_DIR",
    "PAGES",
    "QUESTIONS",
    "OrgProfile",
    "OrgQuestion",
    "SourceError",
    "add_file",
    "add_link",
    "fetch_text",
    "html_to_text",
    "load_profile",
    "org_dir",
    "org_summary",
    "questions_json",
    "save_profile",
]
