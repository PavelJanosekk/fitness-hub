"""RPG layer, step 7.4 (E22): badges, derived from the whole history and the XP ledger (never stored).

A badge unlocks on the first day its condition was met and stays unlocked (also when the level drops later).
"""

import datetime as dt
import re
from dataclasses import dataclass

from sqlmodel import Session

from app.models.habits import HabitFrequency
from app.services import bucket as bk
from app.services import habits as hs
from app.services import quests as qs
from app.services import side_quests as sq
from app.services.rpg import Ledger

MARATHON_KM = 42.0


@dataclass
class Badge:
    key: str
    title: str
    description: str
    unlocked_on: dt.date | None = None
    progress: str | None = None  # for locked badges, e.g. "87 / 100"


def _days(start: dt.date, end: dt.date):
    day = start
    while day <= end:
        yield day
        day += dt.timedelta(days=1)


def _nth(dates: list[dt.date], n: int) -> dt.date | None:
    dates = sorted(dates)
    return dates[n - 1] if len(dates) >= n else None


def compute_badges(session: Session, ledger: Ledger, board: list[hs.HabitDays], on: dt.date) -> list[Badge]:
    history = qs.load_history(session, dt.date(2000, 1, 1), on)
    routine_start = min((d.habit.start_date for d in board), default=on)
    result: list[Badge] = []

    # Routine
    perfect_days = [day for day in _days(routine_start, on) if (r := hs.routine_day(board, day))[1] and r[0] == r[1]]
    result.append(
        Badge(
            "perfect_day", "Perfektní den", "Celá denní rutina za jeden den", perfect_days[0] if perfect_days else None
        )
    )
    perfect = set(perfect_days)
    week, perfect_week = hs.week_start(routine_start), None
    while week + dt.timedelta(days=6) <= on and perfect_week is None:
        if all(week + dt.timedelta(days=i) in perfect for i in range(7)):
            perfect_week = week + dt.timedelta(days=6)
        week += dt.timedelta(weeks=1)
    result.append(Badge("perfect_week", "Perfektní týden", "7 perfektních dní v jednom týdnu", perfect_week))

    best, best_title, streak_30 = 0, None, None
    for item in board:
        if item.habit.frequency != HabitFrequency.daily:
            continue
        run = 0
        for day in _days(item.habit.start_date, on):
            if day in item.done:
                run += 1
            elif day not in item.skip:
                run = 0
            if run > best:
                best, best_title = run, item.habit.title
            if run == 30 and (streak_30 is None or day < streak_30[0]):
                streak_30 = (day, item.habit.title)
    result.append(
        Badge(
            "streak_30",
            "30 dní v kuse",
            f"Jeden návyk 30 dní bez přerušení{f' ({streak_30[1]})' if streak_30 else ''}",
            streak_30[0] if streak_30 else None,
            None if streak_30 else f"nejlepší {best} / 30{f' ({best_title})' if best_title else ''}",
        )
    )

    streak, weeks_10, week = 0, None, hs.week_start(routine_start)
    while week <= on and weeks_10 is None:
        pct = hs.routine_week_pct(board, week, min(on, week + dt.timedelta(days=6))) if board else None
        finished = week + dt.timedelta(days=6) < on
        if pct is not None and pct >= hs.ROUTINE_WEEK_PCT:
            streak += 1
            if streak == 10:
                weeks_10 = min(on, week + dt.timedelta(days=6))
        elif pct is not None and finished:
            streak = 0
        week += dt.timedelta(weeks=1)
    result.append(
        Badge(
            "weeks_10",
            "10 týdnů v řadě",
            f"10 týdnů rutiny nad {hs.ROUTINE_WEEK_PCT} % bez přerušení",
            weeks_10,
            None if weeks_10 else f"{streak} / 10",
        )
    )

    # Training
    workout_days = [day for day, count in history.gym_days.items() for _ in range(count)]
    for n in (100, 250):
        result.append(
            Badge(
                f"workouts_{n}",
                f"{n} tréninků",
                f"{n} tréninků v posilovně",
                _nth(workout_days, n),
                f"{len(workout_days)} / {n}",
            )
        )
    km_year, year_badge = 0.0, None
    by_year: dict[int, float] = {}
    for day, km in sorted(history.runs):
        by_year[day.year] = by_year.get(day.year, 0.0) + km
        if by_year[day.year] >= 1000 and year_badge is None:
            year_badge = day
    km_year = by_year.get(on.year, 0.0)
    result.append(
        Badge(
            "km_1000",
            "1 000 km za rok",
            "1 000 km běhu v jednom kalendářním roce",
            year_badge,
            f"{round(km_year)} / 1 000 km ({on.year})",
        )
    )
    marathon = next((day for day, km in sorted(history.runs) if km >= MARATHON_KM), None)
    result.append(Badge("marathon", "První maraton", "Běh dlouhý alespoň 42 km", marathon))

    # From the ledger
    prs = [e.date for e in ledger.entries if e.kind == "pr"]
    result.append(Badge("prs_50", "50 rekordů", "50 osobních rekordů v posilovně", _nth(prs, 50), f"{len(prs)} / 50"))
    all_quests = next((e.date for e in ledger.entries if e.kind == "quests_all"), None)
    result.append(Badge("quests_all", "Splněné výpravy", "Všechny výpravy jednoho týdne", all_quests))
    reached: dict[int, dt.date] = {}
    for entry in ledger.entries:
        if entry.kind == "level_up" and (match := re.search(r"level (\d+)", entry.text)):
            reached.setdefault(int(match.group(1)), entry.date)
    for level in (10, 20, 30):
        unlocked = next((day for lvl, day in sorted(reached.items()) if lvl >= level), None)
        result.append(Badge(f"level_{level}", f"Level {level}", f"Dosáhni levelu {level}", unlocked))

    result.extend(_bucket_badges(bk.load(session, on)))
    result.extend(_side_quest_badges(sq.load(session, on)))

    for badge in result:
        if badge.unlocked_on:
            badge.progress = None
    return result


def _bucket_badges(state: bk.BucketState) -> list[Badge]:
    """Bucket list (E36): items done before the app count from the day they were added (B6)."""
    done = [s for s in state.items if s.done]
    days = [bk.counted_on(s) for s in done]
    result = [Badge("bucket_first", "První odškrtnutí", "První splněná položka bucket listu", min(days, default=None))]
    for n in (10, 25, 50, 100):
        result.append(
            Badge(
                f"bucket_{n}",
                f"{n} zážitků",
                f"{n} splněných položek bucket listu",
                _nth(days, n),
                f"{len(days)} / {n}",
            )
        )
    legendary = [bk.counted_on(s) for s in done if s.item.rarity == 4]
    result.append(Badge("bucket_legendary", "Legenda", "Splněná legendární položka", min(legendary, default=None)))
    for key, title, category, n in (
        ("gourmet", "Gurmán", "food", 20),
        ("adrenaline", "Adrenalinový junkie", "adrenaline", 5),
    ):
        hits = [bk.counted_on(s) for s in done if s.item.category == category]
        description = f"{n} splněných položek v kategorii {bk.CATEGORY_NAMES[category]}"
        result.append(Badge(key, title, description, _nth(hits, n), f"{len(hits)} / {n}"))
    countries = [c.since for c in state.countries]
    result.append(
        Badge("countries_10", "Cestovatel", "10 zemí na mapě světa", _nth(countries, 10), f"{len(countries)} / 10")
    )
    first: dict[str, dt.date] = {}
    for c in state.countries:
        if c.continent:
            first[c.continent] = min(first.get(c.continent, c.since), c.since)
    continents = list(first.values())
    result.append(
        Badge(
            "continents_7",
            "Všech 7 kontinentů",
            "Navštívené všechny kontinenty",
            _nth(continents, 7),
            f"{len(continents)} / 7",
        )
    )
    years: dict[int, list[dt.date]] = {}
    for s in done:
        if s.xp and s.done_on:
            years.setdefault(s.done_on.year, []).append(s.done_on)
    reached = [d for ds in years.values() if (d := _nth(ds, bk.YEAR_QUEST_ITEMS))]
    best = max((len(ds) for ds in years.values()), default=0)
    result.append(
        Badge(
            "bucket_year",
            "Rok dobrodružství",
            f"{bk.YEAR_QUEST_ITEMS} položek bucket listu za jeden rok",
            min(reached, default=None),
            f"nejvíc {best} / {bk.YEAR_QUEST_ITEMS}",
        )
    )
    return result


SIDE_WEEKS = 10


def _side_quest_badges(states: list[sq.QuestState]) -> list[Badge]:
    """Side quests (E45): quests done before the app count from the day they were added; the weekly streak only
    counts paying completions (like the weekly quest)."""
    days = [s.counted_on for s in states if s.done]
    result = [Badge("side_first", "První side quest", "První splněný side quest", min(days, default=None))]
    for n in (10, 50, 100):
        result.append(
            Badge(f"side_{n}", f"{n} side questů", f"{n} splněných side questů", _nth(days, n), f"{len(days)} / {n}")
        )
    first_in_week: dict[dt.date, dt.date] = {}
    for day in sorted(sq.paying_days(states)):
        first_in_week.setdefault(hs.week_start(day), day)
    streak, best, unlocked, previous = 0, 0, None, None
    for week in sorted(first_in_week):
        streak = streak + 1 if previous == week - dt.timedelta(weeks=1) else 1
        previous, best = week, max(best, streak)
        if streak == SIDE_WEEKS and unlocked is None:
            unlocked = first_in_week[week]
    result.append(
        Badge(
            "side_weeks",
            "Vytrvalý dobrodruh",
            f"Side quest {SIDE_WEEKS} týdnů v řadě",
            unlocked,
            f"nejvíc {best} / {SIDE_WEEKS}",
        )
    )
    near = [s for s in states if s.quest.category == "trip" and (s.quest.travel_minutes or 0) <= sq.NEAR_TRIP_MINUTES]
    near_done = [s.counted_on for s in near if s.done]
    result.append(
        Badge(
            "trips_near",
            "Znalec okolí",
            f"Všechny výlety do {sq.NEAR_TRIP_MINUTES} minut autem",
            max(near_done) if near and len(near_done) == len(near) else None,
            f"{len(near_done)} / {len(near)}",
        )
    )
    return result
