"""Parse structured facts out of the RunningCoach markdown (weekly plan tables, races, LTHR).

The markdown is written for humans, so parsing is deliberately forgiving: rows that don't parse are skipped
and reported as warnings instead of failing the sync.
"""

import datetime as dt
import re
from dataclasses import dataclass, field

DATE_RANGE = re.compile(
    r"(?P<d1>\d{1,2})\.(?:(?P<m1>\d{1,2})\.)?\s*[–-]\s*(?P<d2>\d{1,2})\.(?P<m2>\d{1,2})\.(?P<y>\d{4})?"
)
NUMBER_RANGE = re.compile(r"^\s*~?\s*(\d+(?:[.,]\d+)?)(?:\s*[–-]\s*(\d+(?:[.,]\d+)?))?")
UPDATED = re.compile(r"Aktualizováno:\**\s*(\d{1,2})\.(\d{1,2})\.(\d{4})")
LTHR = re.compile(r"LTHR\s*=\s*\**\s*(\d{3})\s*bpm", re.IGNORECASE)
MAX_HR = re.compile(r"max\s*HR\s*[≥>=]+\s*(\d{3})", re.IGNORECASE)
RACE_LINE = re.compile(
    r"\*\*(Cílový závod|Generálka):\*\*\s*(?P<name>[^,*]+),\s*\**\s*\w+\s+(?P<d>\d{1,2})\.(?P<m>\d{1,2})\.(?P<y>\d{4})"
)
GOAL_LINE = re.compile(r"\*\*Cíl:\*\*\s*(?P<goal>.+?)(?:\n\s*\n|\n\*\*|\Z)", re.DOTALL)  # may wrap lines
QUALITY_COLUMNS = ("kvalita", "náplň")


@dataclass
class ParsedWeek:
    week_start: dt.date
    week_end: dt.date
    block: str | None
    km_text: str | None
    km_min: float | None
    km_max: float | None
    long_run_text: str | None
    long_run_km_min: float | None
    long_run_km_max: float | None
    quality: str | None
    notes: str | None


@dataclass
class ParsedRace:
    name: str
    date: dt.date
    distance_km: float | None
    is_goal_race: bool
    goal: str | None


@dataclass
class ParsedFacts:
    weeks: list[ParsedWeek] = field(default_factory=list)
    races: list[ParsedRace] = field(default_factory=list)
    lthr: int | None = None
    max_hr: int | None = None
    kb_updated: dt.date | None = None
    warnings: list[str] = field(default_factory=list)


def _clean(cell: str) -> str:
    return re.sub(r"\*\*|`", "", cell).strip()


def _number_range(cell: str | None) -> tuple[float | None, float | None]:
    match = NUMBER_RANGE.match(cell or "")
    if not match:
        return None, None
    low = float(match.group(1).replace(",", "."))
    high = float(match.group(2).replace(",", ".")) if match.group(2) else low
    return low, high


def _year_for(day: int, month: int, reference: dt.date) -> int:
    """Plans run forward from the update date: a date more than ~4 months before it belongs to next year."""
    candidate = dt.date(reference.year, month, day)
    return reference.year + 1 if candidate < reference - dt.timedelta(days=120) else reference.year


def parse_date_range(text: str, reference: dt.date) -> tuple[dt.date, dt.date] | None:
    match = DATE_RANGE.search(text)
    if not match:
        return None
    d1, d2, m2 = int(match["d1"]), int(match["d2"]), int(match["m2"])
    m1 = int(match["m1"]) if match["m1"] else m2
    try:
        end_year = int(match["y"]) if match["y"] else _year_for(d2, m2, reference)
        start_year = end_year - 1 if m1 > m2 else end_year
        return dt.date(start_year, m1, d1), dt.date(end_year, m2, d2)
    except ValueError:
        return None


def parse_plan(markdown: str, reference: dt.date) -> tuple[list[ParsedWeek], list[str]]:
    """Weekly rows from every plan table that has km and LR columns, tagged with their '## ' block heading."""
    weeks: list[ParsedWeek] = []
    warnings: list[str] = []
    block: str | None = None
    header: list[str] | None = None
    for raw in markdown.splitlines():
        line = raw.strip()
        if line.startswith("## "):
            block, header = _clean(line[3:].replace("⭐", "")), None
            continue
        if not line.startswith("|"):
            header = None
            continue
        cells = [_clean(c) for c in line.strip("|").split("|")]
        if set("".join(cells)) <= set("-: "):
            continue  # separator row
        lowered = [c.casefold() for c in cells]
        if header is None:
            header = lowered if "km" in lowered and "lr" in lowered else []
            continue
        if not header:
            continue
        row = dict(zip(header, cells, strict=False))
        date_text = row.get("datum") or row.get("týden") or ""
        dates = parse_date_range(date_text, reference)
        if dates is None:
            warnings.append(f"plan row without a date range: {line[:80]}")
            continue
        km_min, km_max = _number_range(row.get("km"))
        lr_min, lr_max = _number_range(row.get("lr"))
        quality = next((row[k] for k in QUALITY_COLUMNS if row.get(k)), None)
        weeks.append(
            ParsedWeek(
                week_start=dates[0],
                week_end=dates[1],
                block=block,
                km_text=row.get("km") or None,
                km_min=km_min,
                km_max=km_max,
                long_run_text=row.get("lr") or None,
                long_run_km_min=lr_min,
                long_run_km_max=lr_max,
                quality=quality,
                notes=row.get("pozn.") or None,
            )
        )
    return weeks, warnings


def parse_index(markdown: str) -> ParsedFacts:
    facts = ParsedFacts()
    if match := UPDATED.search(markdown):
        facts.kb_updated = dt.date(int(match[3]), int(match[2]), int(match[1]))
    if match := LTHR.search(markdown):
        facts.lthr = int(match[1])
    if match := MAX_HR.search(markdown):
        facts.max_hr = int(match[1])
    goal = " ".join(_clean(match["goal"]).split()) if (match := GOAL_LINE.search(markdown)) else None
    for match in RACE_LINE.finditer(markdown):
        name = match["name"].strip()
        is_goal = match[1] == "Cílový závod"
        lowered = name.casefold()
        distance = (
            21.0975
            if "half" in lowered or "půl" in lowered
            else 42.195
            if "marathon" in lowered or "maraton" in lowered
            else None
        )
        facts.races.append(
            ParsedRace(
                name=name,
                date=dt.date(int(match["y"]), int(match["m"]), int(match["d"])),
                distance_km=distance,
                is_goal_race=is_goal,
                goal=goal if is_goal else None,
            )
        )
    for missing, value in (("LTHR", facts.lthr), ("races", facts.races)):
        if not value:
            facts.warnings.append(f"00_INDEX.md: {missing} not found")
    return facts
