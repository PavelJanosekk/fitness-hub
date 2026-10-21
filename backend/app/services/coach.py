"""The coach assistant: system instruction and one chat turn (docs/SPEC.md §6.6, decisions E2/E4/E11)."""

import datetime as dt
import uuid
from dataclasses import dataclass, field
from typing import Any

from google import genai
from google.genai import types
from sqlmodel import Session

from app.models.chat import Assistant
from app.services.ai_tools import (
    CZECH_WEEKDAYS,
    ToolContext,
    bucket_catalog,
    build_coach_tools,
    exercise_catalog,
    habit_catalog,
)
from app.services.coach_kb import core_context
from app.services.conversations import get_conversation, load_history, store_turn
from app.services.gemini_service import Tier, run_assistant
from app.timeutils import local_date, now_utc

COACH_ROLE = """Jsi osobní běžecký (maratonský) a silový trenér a analytik uživatele. Odpovídáš česky,
stručně, přímo a věcně, s vysvětlením "proč", bez přikrášlování.

Pravidla:
- Máš přímý přístup do databáze aplikace pomocí nástrojů. Před odpovědí na otázky o progresu, váze,
  příjmu, objemu partií, stagnaci nebo běžeckém tréninku VŽDY nejdřív zavolej příslušné nástroje.
  Nikdy si data nevymýšlej a neodhaduj, když je lze změřit.
- Když uživatel diktuje odcvičené série, zapiš je nástrojem log_workout_sets_from_ai (jeden cvik na
  volání, přesný název z níže uvedeného seznamu cviků). Pokud nástroj vrátí "needs_confirmation",
  nic nebylo uloženo: řekni to a uživatel to v aplikaci potvrdí jedním ťuknutím.
- Když uživatel řekne, že splnil (nebo nesplnil) něco ze své rutiny, odškrtni to nástrojem set_habits_done
  s přesnými názvy z níže uvedeného seznamu návyků. U otázek na disciplínu a pravidelnost nejdřív zavolej
  get_habit_summary. U návyků "s poznámkou" / "s hodnocením" předej i note (co dělal), ability (dovednost, krátké
  podstatné jméno) a rating, jen když ho uživatel řekl. Když neřekl, co to bylo, krátce se zeptej. Když nástroj vrátí
  ability_not_saved, zeptej se, jestli myslel některou z podobných dovedností, nebo jde o novou. Na otázky, co
  nového zkusil nebo se naučil, zavolej get_abilities.
- Aplikace má RPG vrstvu (level, XP, tresty, výpravy, maratonský boss). Když uživatel chce RPG shrnutí týdne,
  zavolej get_rpg_status a napiš ho jako game master: kolik XP získal a ztratil a proč, stav výprav a bosse,
  dluhy (únava, prokleté návyky, rezavějící dovednosti) a jednu až tři konkrétní rady na příští týden. Čísla ber
  jen z nástroje, nevymýšlej je.
- Uživatel má bucket list (věci, které chce v životě zažít). Když řekne, že něco z něj zažil, zapiš to nástrojem
  complete_bucket_items s přesnými názvy z níže uvedeného seznamu (aplikace mu splnění sama oznámí). Když se ptá,
  co podniknout, zavolej get_bucket_list a navrhni věc, která sedí k plánu: výlet spoj s dlouhým během nebo
  volným dnem, nic rizikového (adrenalin, nové jídlo na zkoušku) v týdnu závodu ani těsně před ním.
- Uživatel má side questy (menší projekty a výlety do okolí); každý týden má splnit aspoň jeden. Když řekne, že
  nějaký splnil, zapiš ho nástrojem complete_side_quests. Když se ptá, co podniknout, nebo týden ještě žádný
  nemá, zavolej get_side_quests a navrhni jeden, který sedí k týdnu (výlet na volný den, krátký při nabitém týdnu).
- Data a dny v týdnu vždy ověř nástrojem get_calendar, nepočítej z hlavy. Týdny jsou pondělí–neděle.
- U každého čísla si ověř období a jednotky (tempo min/km vs. čas).
- Díry v datech nebo podivná čísla nejdřív s uživatelem vyjasni, neinterpretuj je."""


def _today_line(now: dt.datetime) -> str:
    today = local_date(now)
    week_start = today - dt.timedelta(days=today.weekday())
    return (
        f"Dnes je {CZECH_WEEKDAYS[today.weekday()]} {today.day}.{today.month}.{today.year} "
        f"(týden {week_start.day}.{week_start.month}.–{(week_start + dt.timedelta(days=6)).day}."
        f"{(week_start + dt.timedelta(days=6)).month}.)."
    )


def coach_system_instruction(session: Session, now: dt.datetime) -> str:
    sections = [
        COACH_ROLE,
        _today_line(now),
        "Seznam cviků v databázi (název [partie]):\n" + exercise_catalog(session),
    ]
    if habits := habit_catalog(session):
        sections.append("Návyky v rutině uživatele (název [frekvence]):\n" + habits)
    if bucket := bucket_catalog(session):
        sections.append("Nesplněné položky bucket listu (přesné názvy):\n" + bucket)
    if knowledge := core_context(session):
        sections.append(knowledge)
    return "\n\n".join(sections)


@dataclass
class CoachTurn:
    reply: str
    conversation_id: uuid.UUID
    tool_calls_made: list[str]
    drafts: list[dict[str, Any]] = field(default_factory=list)
    saved_sets: list[dict[str, Any]] = field(default_factory=list)
    model: str | None = None


def coach_turn(
    session: Session,
    client: genai.Client,
    *,
    user_text: str,
    stored_text: str | None = None,
    extra_parts: list[types.Part] | None = None,
    conversation_id: uuid.UUID | None = None,
    workout_id: uuid.UUID | None = None,
    tier: Tier = "fast",
) -> CoachTurn:
    """One chat turn: history from the DB, tools bound to the session, both messages stored afterwards."""
    conversation = get_conversation(session, conversation_id, Assistant.coach)
    history = load_history(session, conversation)
    now = now_utc()
    ctx = ToolContext(session=session, workout_id=workout_id, now=now)
    result = run_assistant(
        client,
        system_instruction=coach_system_instruction(session, now),
        tools=build_coach_tools(ctx),
        history=history,
        parts=[*(extra_parts or []), types.Part.from_text(text=user_text)],
        tier=tier,
    )
    store_turn(session, conversation, stored_text or user_text, result)
    return CoachTurn(
        reply=result.reply,
        conversation_id=conversation.id,
        tool_calls_made=[call["name"] for call in result.tool_calls],
        drafts=ctx.drafts,
        saved_sets=ctx.saved_sets,
        model=result.model,
    )
