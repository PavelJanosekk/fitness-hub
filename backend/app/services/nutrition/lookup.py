"""Smart lookup for dishes the database doesn't know (E30): a recipe from the web, computed from USDA foods.

1. DuckDuckGo's HTML search for "<dish> recept" (no API key; unofficial, so any failure just falls through),
   then the first result pages that carry a schema.org Recipe in JSON-LD (toprecepty.cz, iprima, recipetineats…).
2. One Gemini lite call turns the ingredient lines into grams + USDA-style queries, with each ingredient's weight
   in the finished dish (a single overall estimate came out far too low in the live check: 900 g for ~1.6 kg of
   Bún chả) and the portions. Without a web recipe it writes a typical one.
3. Each ingredient resolves to a local USDA food, and the dish is their sum over the finished weight
   (`recipes.py`). Gemini never supplies nutrient numbers, and the page's own nutrition values are ignored
   (user decision).
"""

import datetime as dt
import html
import ipaddress
import json
import logging
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urljoin, urlsplit

import httpx
from google.genai import types
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.models.nutrition import FoodSource
from app.services.gemini_service import lite_model
from app.services.nutrition.nutrients import MACROS
from app.services.nutrition.recipes import Part, finished_weight, per_100g, recipe_info
from app.services.nutrition.resolver import Candidate, MealItemInput, normalize, search_usda
from app.timeutils import now_utc

log = logging.getLogger(__name__)

SEARCH_URL = "https://html.duckduckgo.com/html/"
# The HTML endpoint answers bare clients with an anomaly page, recipe sites sometimes too
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
    "Accept-Language": "cs,en;q=0.7",
}
TIMEOUT = 8
MAX_PAGES = 3  # result pages tried for a recipe
MAX_BYTES = 3_000_000
MAX_REDIRECTS = 3
SKIP_HOSTS = ("duckduckgo.com", "youtube.com", "facebook.com", "instagram.com", "tiktok.com", "pinterest.")
MAX_LINES = 40
MIN_SCORE = 0.6  # search_usda score below which an ingredient counts as unresolved (as the micros mapper)
MIN_RESOLVED = 0.75  # share of the ingredient mass that has to resolve, or the dish isn't computed
# DuckDuckGo's bot check (202) blocked the server for well over 10 minutes after ~10 quick searches (2026-10-19):
# after one, searching pauses instead of prolonging the block, and the typical recipe is used meanwhile
SEARCH_PAUSE = dt.timedelta(minutes=30)
BLOCKED = {202, 403, 429}
CACHE_SIZE = 100

RESULT_LINK = re.compile(r"<a\b[^>]*\bclass=\"result__a\"[^>]*>", re.IGNORECASE)
HREF = re.compile(r"\bhref=\"([^\"]+)\"")
LD_JSON = re.compile(r"<script[^>]*type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>", re.DOTALL | re.IGNORECASE)
TAG = re.compile(r"<[^>]+>")

RECIPE_PROMPT = """Počítáme nutriční hodnoty jídla "{name}" (uživatel řekl: "{phrase}") z receptu. Vrať všechny
suroviny receptu:
- name_cs: surovina česky.
- usda_query_en: anglický název potraviny ve stylu USDA SR Legacy ve stavu, v jakém ji recept odměřuje
  (např. "Pork, fresh, belly, raw", "Rice noodles, dry", "Sauce, fish, ready-to-serve", "Salt, table");
  voda = "Beverages, water, tap, drinking".
- grams: množství v gramech (1 lžíce ≈ 15 g, oleje 13 g, 1 lžička ≈ 5 g, 1 stroužek česneku ≈ 4 g,
  1 cibule ≈ 100 g, 1 vejce ≈ 50 g). U rozmezí vezmi střed. Když množství chybí, odhadni obvyklé množství
  pro tento recept a dej assumed=true, jinak assumed=false.
- grams_in_dish: kolik surovina váží v hotovém jídle. Suché těstoviny, nudle a rýže po uvaření zhruba
  2,5× až 3× víc, luštěniny 2,5×; maso po pečení, grilování nebo smažení zhruba 0,7×; syrová zelenina,
  omáčky a ostatní stejně jako grams.
- Olej na smažení jen ta část, kterou jídlo nasaje; zálivka nebo omáčka k namáčení jen ta část, která se sní.
- Mezititulky ("Na marinádu:") nejsou suroviny.
- portions: počet porcí, pro které recept je.

"""
WEB_RECIPE = "Recept „{title}“ ({url}), {servings}:\n{lines}"
TYPICAL_RECIPE = "Recept nemáme: použij typický recept tohoto jídla na 1 porci, jak se běžně podává (portions = 1)."


class Ingredient(BaseModel):
    name_cs: str = Field(min_length=1, max_length=120)
    usda_query_en: str = Field(min_length=2, max_length=200)
    # ge, not gt: Gemini's response schema rejects exclusiveMinimum; zero amounts are skipped
    grams: float = Field(ge=0, le=5000)
    grams_in_dish: float = Field(ge=0, le=15000, description="Weight in the finished dish (after cooking)")
    assumed: bool = Field(description="The recipe gives no amount: estimated")


class RecipePlan(BaseModel):
    ingredients: list[Ingredient]
    portions: float = Field(ge=0, le=50)


@dataclass
class WebRecipe:
    url: str
    title: str
    ingredients: list[str]
    servings: str | None


class SearchState:
    """Per process: recipes already found by dish (the chat and "Dohledat recept" often ask twice) and the pause
    after a bot check."""

    def __init__(self) -> None:
        self.paused_until: dt.datetime | None = None
        self.recipes: dict[str, WebRecipe] = {}


state = SearchState()


def _public(url: str) -> bool:
    """A web page worth fetching: http(s) on a host name, not an address or this machine."""
    parts = urlsplit(url)
    host = parts.hostname or ""
    if parts.scheme not in ("http", "https") or not host or host == "localhost" or "." not in host:
        return False
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return True
    return False


def result_urls(page: str) -> list[str]:
    """Organic result links of a DuckDuckGo HTML page (they go through its /l/?uddg= redirect; ads are skipped)."""
    urls: list[str] = []
    for tag in RESULT_LINK.findall(page):
        if (href := HREF.search(tag)) is None:
            continue
        link = html.unescape(href.group(1))
        target = parse_qs(urlsplit(link).query).get("uddg", [link])[0]
        host = urlsplit(target).hostname or ""
        if _public(target) and not any(skip in host for skip in SKIP_HOSTS) and target not in urls:
            urls.append(target)
    return urls


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", TAG.sub(" ", html.unescape(str(value)))).strip()


def _find_recipe(node: Any, depth: int = 0) -> dict[str, Any] | None:
    if depth > 6:
        return None
    if isinstance(node, dict):
        kind = node.get("@type")
        if kind == "Recipe" or (isinstance(kind, list) and "Recipe" in kind):
            return node
        children = list(node.values())
    elif isinstance(node, list):
        children = node
    else:
        return None
    for child in children:
        if (found := _find_recipe(child, depth + 1)) is not None:
            return found
    return None


def parse_recipe(page: str, url: str) -> WebRecipe | None:
    """The first schema.org Recipe in the page's JSON-LD with at least two ingredient lines."""
    for block in LD_JSON.findall(page):
        try:
            recipe = _find_recipe(json.loads(block.strip(), strict=False))
        except json.JSONDecodeError:
            continue
        if recipe is None:
            continue
        raw = recipe.get("recipeIngredient") or recipe.get("ingredients") or []
        lines = [_text(line)[:200] for line in ([raw] if isinstance(raw, str) else raw) if isinstance(line, str)]
        lines = [line for line in lines if line][:MAX_LINES]
        if len(lines) < 2:
            continue
        servings = recipe.get("recipeYield")
        if isinstance(servings, list):
            servings = max((str(s) for s in servings if s), key=len, default=None)  # ["2", "2 porce"] → "2 porce"
        return WebRecipe(url, _text(recipe.get("name") or "")[:200], lines, _text(servings)[:60] if servings else None)
    return None


def fetch_page(http: httpx.Client, url: str) -> tuple[str, str] | None:
    """(final url, html) of a public page, following a few redirects that stay public; None on any problem."""
    for _ in range(MAX_REDIRECTS + 1):
        if not _public(url):
            return None
        try:
            with http.stream("GET", url, headers=HEADERS, timeout=TIMEOUT) as response:
                if response.is_redirect and (location := response.headers.get("location")):
                    url = urljoin(url, location)
                    continue
                if response.status_code != 200 or "html" not in response.headers.get("content-type", ""):
                    return None
                body = b""
                for chunk in response.iter_bytes():
                    body += chunk
                    if len(body) > MAX_BYTES:
                        return None
                return url, body.decode(response.encoding or "utf-8", errors="replace")
        except httpx.HTTPError:
            return None
    return None


def find_web_recipe(http: httpx.Client, dish: str) -> WebRecipe | None:
    key = normalize(dish)
    if (known := state.recipes.get(key)) is not None:
        return known
    if state.paused_until is not None and now_utc() < state.paused_until:
        return None
    try:
        # kl = region: Czech recipes (Czech portions and ingredients) first
        response = http.get(SEARCH_URL, params={"q": f"{dish} recept", "kl": "cz-cs"}, headers=HEADERS, timeout=TIMEOUT)
    except httpx.HTTPError as exc:
        log.info("recipe search unavailable: %s", exc)
        return None
    if response.status_code != 200:
        if response.status_code in BLOCKED:  # 202 = DuckDuckGo's rate limit / bot check
            state.paused_until = now_utc() + SEARCH_PAUSE
        log.info("recipe search answered %s", response.status_code)
        return None
    for url in result_urls(response.text)[:MAX_PAGES]:
        if (page := fetch_page(http, url)) is not None and (recipe := parse_recipe(page[1], page[0])) is not None:
            if len(state.recipes) >= CACHE_SIZE:
                state.recipes.clear()
            state.recipes[key] = recipe
            return recipe
    return None


def plan_recipe(client: Any, item: MealItemInput, recipe: WebRecipe | None) -> RecipePlan | None:
    """Ingredient grams + USDA queries for the web recipe (or a typical one). Gemini errors propagate."""
    if recipe is not None:
        servings = f"počet porcí: {recipe.servings}" if recipe.servings else "počet porcí neuveden"
        lines = "\n".join(f"- {line}" for line in recipe.ingredients)
        source = WEB_RECIPE.format(title=recipe.title, url=recipe.url, servings=servings, lines=lines)
    else:
        source = TYPICAL_RECIPE
    response = client.models.generate_content(
        model=lite_model(),
        contents=RECIPE_PROMPT.format(name=item.canonical_name_cs, phrase=item.user_phrase) + source,
        config=types.GenerateContentConfig(
            response_mime_type="application/json", response_schema=RecipePlan, temperature=0
        ),
    )
    return response.parsed if isinstance(response.parsed, RecipePlan) else None


def compute(session: Session, item: MealItemInput, plan: RecipePlan, source_url: str | None) -> Candidate | None:
    """The dish as a draft candidate; None when too little of it resolves to USDA foods or the result is absurd."""
    parts, cooked = [], 0.0
    for ingredient in plan.ingredients:
        if ingredient.grams <= 0:
            continue
        hits = search_usda(session, ingredient.usda_query_en, limit=1, include_hidden=True)
        food = hits[0][0] if hits and hits[0][1] >= MIN_SCORE else None
        parts.append(Part(ingredient.name_cs, ingredient.grams, food, ingredient.assumed))
        cooked += ingredient.grams_in_dish
    total = sum(p.grams for p in parts)
    if total <= 0 or sum(p.grams for p in parts if p.food) < MIN_RESOLVED * total:
        return None
    yield_g = finished_weight(parts, cooked)
    values = per_100g(parts, yield_g)
    if values["kcal"] > 900:
        return None
    per_100g_all: dict[str, float | None] = {n.key: values.get(n.key) for n in MACROS}
    recipe = recipe_info(parts, yield_g, plan.portions if plan.portions >= 1 else 1, source_url)
    return Candidate("recipe", item.canonical_name_cs, FoodSource.recipe, per_100g_all, score=0.4, recipe=recipe)


def lookup_dish(session: Session, http: httpx.Client | None, client: Any, item: MealItemInput) -> Candidate | None:
    """A web recipe (or Gemini's typical one) computed from USDA foods. Gemini errors propagate."""
    web = find_web_recipe(http, item.canonical_name_cs) if http is not None else None
    plan = plan_recipe(client, item, web)
    return compute(session, item, plan, web.url if web else None) if plan is not None else None
