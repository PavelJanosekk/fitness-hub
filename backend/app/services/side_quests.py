"""Side quests (E45, docs/side-quests-module-spec.md): what a completed side quest pays and the weekly rhythm.

XP (tune): a quest pays by its duration on its completion day, to its category's skill. No XP for quests done
before the app (`done_before_app`) or completed more than LATE_DAYS before they were added (as the bucket list).
The weekly quest "1 side quest" (any duration) lives in services/quests.py; no penalties here.
"""

import datetime as dt
from dataclasses import dataclass

from sqlmodel import Session, col, select

from app.models.side_quests import SideQuest, SideQuestCategory, SideQuestDuration
from app.services.bucket import LATE_DAYS
from app.timeutils import local_date

DURATIONS = {
    SideQuestDuration.moment: ("Chvilka", 20),
    SideQuestDuration.day: ("1 den", 50),
    SideQuestDuration.weekend: ("Víkend", 120),
    SideQuestDuration.week: ("Týden", 250),
    SideQuestDuration.month: ("Měsíc+", 500),
}
CATEGORIES = {  # name, RPG skill
    SideQuestCategory.learn: ("Učení", "mind"),
    SideQuestCategory.make: ("Tvoření", "mind"),
    SideQuestCategory.food: ("Jídlo", "nutrition"),
    SideQuestCategory.activity: ("Aktivita", "adventure"),
    SideQuestCategory.trip: ("Výlet", "adventure"),
}
NEAR_TRIP_MINUTES = 60  # badge: every trip within an hour's drive


@dataclass
class QuestState:
    quest: SideQuest
    xp: int = 0  # what it paid; 0 when open or not paying

    @property
    def done(self) -> bool:
        return self.quest.done_before_app or self.quest.done_on is not None

    @property
    def counted_on(self) -> dt.date:
        """For badges: quests done before the app count from the day they were added."""
        return self.quest.done_on or local_date(self.quest.created_at)

    @property
    def skill(self) -> str:
        return CATEGORIES[SideQuestCategory(self.quest.category)][1]


def full_xp(quest: SideQuest) -> int:
    return DURATIONS[SideQuestDuration(quest.duration)][1]


def pays(quest: SideQuest) -> bool:
    return (
        quest.done_on is not None
        and not quest.done_before_app
        and quest.done_on >= local_date(quest.created_at) - dt.timedelta(days=LATE_DAYS)
    )


def load(session: Session, on: dt.date) -> list[QuestState]:
    states = []
    for quest in session.exec(select(SideQuest).order_by(col(SideQuest.id))):
        if quest.done_on is not None and quest.done_on > on:
            quest = quest.model_copy(update={"done_on": None})  # completed later than `on`: open as of then
        states.append(QuestState(quest, full_xp(quest) if pays(quest) else 0))
    return states


@dataclass
class Gain:
    date: dt.date
    amount: int
    kind: str
    text: str
    skill: str


def gains(states: list[QuestState]) -> list[Gain]:
    return [
        Gain(
            s.quest.done_on,
            s.xp,
            "side_quest",
            f"Side quest: {s.quest.title} ({DURATIONS[SideQuestDuration(s.quest.duration)][0]})",
            s.skill,
        )
        for s in states
        if s.xp and s.quest.done_on
    ]


def paying_days(states: list[QuestState]) -> list[dt.date]:
    """Completion days of the quests that count for the weekly quest (the same ones that pay XP)."""
    return [s.quest.done_on for s in states if s.xp and s.quest.done_on]
