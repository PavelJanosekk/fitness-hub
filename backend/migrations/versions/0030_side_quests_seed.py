"""side quests: categories by content and the user's list

The user's side-quest list of 2026-10-21 (`Typ,Kategorie,Úkol,Stav`, 189 rows; the original types were only
"1 den" / "Dlouhodobé" and the categories a quick split) seeded once, cleaned up like the bucket list (B7): Czech
titles, a duration judged per row, categories by content, duplicates merged, items already on the bucket list left
out (Brew Beer, own pasta, handstand, volunteering x2). Rows marked Hotovo are `done_before_app` (no XP).

The provisional category "activity" is split into explore / people / self / move / home; new are skill, move,
explore, people, self, home (E45 follow-up).

Revision ID: 0030
Revises: 0029
Create Date: 2026-10-21 17:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0030"
down_revision: str | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD = "('learn', 'make', 'food', 'activity', 'trip')"
NEW = "('learn', 'skill', 'make', 'food', 'move', 'explore', 'people', 'self', 'home', 'trip')"

M, D, W, T, L = "moment", "day", "weekend", "week", "month"  # Chvilka, 1 den, Víkend, Týden, Měsíc+
DONE = True
# (category, duration, title, note, done before the app)
SEED: list[tuple[str, str, str, str | None, bool]] = [
    # Učení: how things work, history, ideas
    ("learn", D, "Dokument o tématu, o kterém nic nevím", None, False),
    ("learn", M, "Zjistit, jak doopravdy funguje nějaká běžná věc", None, False),
    ("learn", W, "1. světová válka do hloubky", None, False),
    ("learn", W, "2. světová válka do hloubky", "Včetně toho, v co věřil Hitler a proč to lidi táhlo.", False),
    ("learn", D, "Univerzitní přednáška mimo můj obor", None, False),
    ("learn", D, "Jak fungují daně v Česku", None, False),
    ("learn", D, "Poznat 10 souhvězdí", "Na noční obloze, ne jen z knížky.", False),
    ("learn", D, "Jak funguje internet od začátku do konce", None, False),
    ("learn", W, "Základy filozofie", "Stoicismus, existencialismus a další.", False),
    ("learn", D, "Historie mého města", None, False),
    ("learn", M, "Jak se dělají mapy", None, False),
    ("learn", D, "Jak funguje pojištění", None, False),
    ("learn", D, "Jak funguje propaganda", None, False),
    ("learn", D, "Jedna historická událost ze tří pohledů", None, False),
    ("learn", D, "Jak funguje paměť", None, False),
    ("learn", D, "Víra, kterou nesdílím: přečíst si o ní", None, False),
    ("learn", M, "Jak funguje GPS", None, False),
    ("learn", M, "Jak fungují čárové kódy", None, False),
    ("learn", M, "Jak fungují mikrofony", None, False),
    ("learn", D, "Ptáci v okolí: poznat je", None, False),
    ("learn", D, "Místní ekosystém", None, False),
    ("learn", M, "Typy mraků: pozorovat a pojmenovat", None, False),
    ("learn", M, "Jak roční období ovlivňují náladu", None, False),
    ("learn", M, "Jak se rozhoduje o přijetí do práce", None, False),
    ("learn", D, "Projektové řízení: základy", None, False),
    ("learn", D, "Proč týmy selhávají", None, False),
    ("learn", D, "Styly vedení lidí", None, False),
    ("learn", M, "Jak vzniká vyhoření", None, False),
    ("learn", M, "Časová pásma do hloubky", None, False),
    ("learn", M, "Stolování v cizích zemích", None, False),
    ("learn", M, "Kulturní tabu", None, False),
    ("learn", D, "Králičí nora: jedno náhodné téma do hloubky", None, False),
    ("learn", D, "Jak selhávají systémy a jak vznikají chyby", None, False),
    ("learn", M, "Serendipita: šťastné náhody", None, False),
    ("learn", T, "Sbírka zajímavostí: 20 faktů", None, False),
    ("learn", M, "Default mode network: co dělá mozek v klidu", None, False),
    ("learn", M, "Jak trénují experti (deliberate practice)", None, False),
    ("learn", M, "Pětkrát náhodná stránka na Wikipedii", None, False),
    ("learn", L, "Číst knihy pravidelně", "Např. kniha měsíčně.", False),
    ("learn", D, "Jak doopravdy funguje spánek", None, DONE),
    ("learn", D, "Jak se dělá předpověď počasí", None, DONE),
    ("learn", D, "Jak fungují motory (základy)", None, DONE),
    # Dovednosti: practical skills
    ("skill", D, "Naučit se zpaměti báseň, citát nebo projev", None, False),
    ("skill", D, "Základní fráze ve znakové řeči", None, False),
    ("skill", D, "Kouzelnický nebo party trik", None, False),
    ("skill", M, "Psát na telefonu rychleji a bez překlepů", None, False),
    ("skill", D, "První pomoc: základy", None, False),
    ("skill", D, "Kompozice fotky: základy", None, False),
    ("skill", T, "Jedna písnička na nástroj", None, False),
    ("skill", D, "Šití: základy", None, False),
    ("skill", D, "Základní údržba auta", None, False),
    ("skill", D, "Slušně vyjednávat", None, False),
    ("skill", D, "Zbytečná, ale zábavná dovednost", None, False),
    ("skill", D, "Mluvení před lidmi: základní techniky", None, False),
    ("skill", M, "Jedna praktická zkratka, kterou začnu používat", None, False),
    ("skill", M, "Vysvětlit svou práci jednoduše", None, False),
    ("skill", D, "Dávat konstruktivní zpětnou vazbu", None, False),
    ("skill", D, "Origami zvířátka", None, False),
    ("skill", D, "Kurz", "Jakýkoli, který mě láká.", False),
    ("skill", D, "Kurz speciální jízdy", "Bezpečná jízda, smyk, okruh…", False),
    ("skill", T, "Neobvyklý řidičák", "Loď, vysokozdvižný vozík…", False),
    ("skill", M, "Speedrun obyčejné činnosti", None, False),
    ("skill", L, "Naučit se tančit", None, False),
    ("skill", L, "Naučit se shuffle", None, False),
    ("skill", T, "Pískání na prsty", None, False),
    ("skill", L, "2 000 slovíček v novém jazyce", None, False),
    ("skill", T, "Žonglování", None, False),
    ("skill", T, "Složit Rubikovu kostku", None, False),
    ("skill", L, "Stát se expertem na jedno téma", "Ten, za kým lidi chodí.", False),
    ("skill", L, "Mistrovská úroveň v jedné úzké oblasti", None, False),
    ("skill", L, "Vzácné a cenné dovednosti", None, False),
    # Tvoření
    ("make", W, "Rodinná kuchařka", None, False),
    ("make", L, "Vytvořit něco, co mě přežije", None, False),
    ("make", D, "Lego", None, False),
    ("make", D, "Osobní mapa oblíbených míst", "Klidně i mentální mapa města.", False),
    ("make", D, "Upravit nebo ozdobit věc, kterou denně používám", None, False),
    ("make", W, "Fotokniha", None, False),
    ("make", D, "Něco jen z recyklovaných materiálů", None, False),
    ("make", W, "Vlog z výletu", None, False),
    ("make", M, "Sdílet svůj výtvor veřejně", None, False),
    ("make", D, "Napodobit něco, co obdivuju", None, False),
    ("make", L, "Vytvořit hru", None, False),
    ("make", W, "Druhý mozek: systém na poznámky", None, False),
    ("make", L, "Jedna zajímavá fotka každý měsíc", None, False),
    ("make", T, "Týden dokumentovat svůj den", None, False),
    ("make", D, "Puzzle", None, DONE),
    # Jídlo
    ("food", D, "Upéct něco", None, False),
    ("food", D, "Celé jídlo od nuly", None, False),
    ("food", D, "Tradiční snídaně jiné kultury", None, False),
    ("food", D, "Jídlo z kultury, o které nic nevím", None, False),
    ("food", T, "Naučit se 5 základních jídel", None, False),
    ("food", D, "Práce s nožem: základy", None, DONE),
    # Pohyb
    ("move", D, "Běh na 5 km v kostýmu", None, False),
    ("move", D, "Zkusit bojové umění", None, False),
    ("move", W, "Bikepacking", None, False),
    ("move", D, "Nový druh pohybu", "Lezení, plavání, jóga…", False),
    ("move", T, "Skákání přes švihadlo", None, False),
    # Objevování: places and the town
    ("explore", D, "Mimo bublinu: prozkoumat MHD", None, False),
    ("explore", D, "Místo ve městě, kde jsem nikdy nebyl", None, False),
    ("explore", D, "Východ slunce z nového místa", None, False),
    ("explore", M, "Procházka při západu slunce", None, False),
    ("explore", M, "Neznámá cesta: jít, kam vede", None, False),
    ("explore", D, "Sólo mikro-dobrodružství na jedno odpoledne", None, False),
    ("explore", D, "Nejvyšší veřejně přístupné místo v okolí", None, False),
    ("explore", D, "Prozkoumat své město jako turista", None, False),
    ("explore", D, "Muzeum o samotě", None, False),
    ("explore", D, "Nejstarší budova v okolí", None, False),
    ("explore", D, "Místní akce, kterou bych normálně vynechal", None, False),
    ("explore", D, "Hodina autem bez cíle", None, False),
    ("explore", D, "Malé městečko v okolí", None, False),
    ("explore", D, "Veřejné umění ve městě", None, False),
    ("explore", D, "Historická památka v okolí", None, False),
    ("explore", D, "Fotit jen dveře a okna", None, False),
    ("explore", M, "Jít někam jen proto, že to vypadá zajímavě", None, False),
    ("explore", D, "Město bez GPS", None, False),
    ("explore", D, "Jedno místo dvakrát: všimnout si rozdílů", None, False),
    ("explore", D, "Místo z dětství", None, False),
    ("explore", M, "Dlouhá procházka bez hudby a telefonu", None, False),
    ("explore", D, "Poznat 10 místních rostlin nebo stromů", None, False),
    ("explore", L, "Sledovat Měsíc celý cyklus", None, False),
    ("explore", L, "Cesta, která posune moje hranice", None, False),
    # Lidé
    ("people", M, "Upřímně pochválit pět lidí", None, False),
    ("people", M, "Ozvat se někomu, s kým jsem dlouho nemluvil", None, False),
    ("people", D, "Potkat naživo kamaráda z internetu", None, False),
    ("people", M, "Pomoct někomu, aniž by o to žádal", None, False),
    ("people", T, "Přidat se do klubu nebo skupiny", None, False),
    ("people", D, "Jít sám na meetup", None, False),
    ("people", M, "Rada od někoho staršího", None, False),
    ("people", M, "Rada od někoho mladšího", None, False),
    ("people", D, "Pamatovat si jména lidí", None, False),
    ("people", D, "Jídlo s někým novým", None, False),
    ("people", D, "Naučit někoho životní dovednost", None, False),
    ("people", M, "Navrhnout plány někomu novému", None, False),
    ("people", M, "Ozvat se ve skupině, i když je to nepříjemné", None, False),
    ("people", M, "Udělat něco trochu nepříjemného společensky", None, False),
    ("people", L, "Změnit někomu život k lepšímu", None, False),
    ("people", M, "Náhodný dobrý skutek", None, DONE),
    # Sebepoznání: reflection, comfort zone, habits of mind
    ("self", D, "Den bez sociálních sítí", None, False),
    ("self", D, "Celý den offline", "Bez internetu, telefon jen na nouzové případy.", False),
    ("self", D, "Malý krok k jednomu strachu", None, False),
    ("self", D, "Malý cíl a splnit ho ještě ten den", None, False),
    ("self", D, "Něco nepříjemného, ale prospěšného", None, False),
    ("self", M, "Mých 5 hlavních hodnot a proč", None, False),
    ("self", M, "50 věcí, za které jsem vděčný", None, False),
    ("self", M, "30 minut nicnedělání", "Žádné podněty.", False),
    ("self", M, "Zpochybnit jeden svůj celoživotní předpoklad", None, False),
    ("self", M, "Kde v mém životě hrálo roli štěstí", None, False),
    ("self", M, "Test osobnosti nebo silných stránek", None, False),
    ("self", M, "Jak zvládám těžké chvíle (coping)", None, False),
    ("self", M, "Odkud se vzal můj obraz sebe sama", None, False),
    ("self", D, "Zkusit něco, o čem si myslím, že mě nebude bavit", None, False),
    ("self", D, "Trénovat snášení nejistoty", None, False),
    ("self", D, "Záměrně změnit názor", None, False),
    ("self", D, "Být začátečník: dělat něco, v čem jsem špatný", None, False),
    ("self", D, "Zlepšit jeden denní systém", None, False),
    ("self", D, "Automatizovat nebo delegovat něco podstatného", None, False),
    ("self", D, "Přihlásit se do něčeho soutěžního", None, False),
    ("self", D, "Roční ohlédnutí jako rituál", None, False),
    ("self", D, "Den v oblečení mimo svou normu", None, False),
    ("self", T, "Nová záliba na týden", None, False),
    ("self", T, "Týden sledovat náladu", None, False),
    ("self", L, "30denní výzva", None, False),
    ("self", L, "Dlouhodobý experiment na sobě", None, False),
    ("self", L, "Proměnit velkou slabinu v silnou stránku", None, False),
    ("self", D, "Najít důvod obléct si outfit, který jinak nemám kam vzít", None, DONE),
    # Domov
    ("home", D, "Uklidit místo, které je dlouho v nepořádku", None, False),
    ("home", D, "Vyklidit celou jednu místnost", None, False),
    ("home", D, "Opravit rozbitou věc místo vyhození", None, False),
    ("home", D, "Základní údržba domácnosti", None, False),
    ("home", M, "Elektřina doma: základy bezpečnosti", None, False),
    ("home", M, "Prodat něco, co nepotřebuju", None, False),
    ("home", L, "Starat se o jednu rostlinu", None, False),
]


def upgrade() -> None:
    op.drop_constraint(op.f("ck_side_quests_category"), "side_quests", type_="check")
    op.execute("UPDATE side_quests SET category = 'explore' WHERE category = 'activity'")
    op.create_check_constraint(op.f("ck_side_quests_category"), "side_quests", f"category IS NULL OR category IN {NEW}")
    bind = op.get_bind()
    for category, duration, title, note, done in SEED:
        bind.execute(
            sa.text(
                "INSERT INTO side_quests (title, category, duration, note, active, done_before_app, created_at)"
                " VALUES (:title, :category, :duration, :note, false, :done, now())"
            ),
            {"title": title, "category": category, "duration": duration, "note": note, "done": done},
        )


def downgrade() -> None:
    bind = op.get_bind()
    for _, _, title, _, _ in SEED:
        bind.execute(sa.text("DELETE FROM side_quests WHERE title = :title"), {"title": title})
    op.drop_constraint(op.f("ck_side_quests_category"), "side_quests", type_="check")
    op.execute("UPDATE side_quests SET category = 'learn' WHERE category IN ('skill', 'self')")
    op.execute("UPDATE side_quests SET category = 'activity' WHERE category IN ('move', 'explore', 'people', 'home')")
    op.create_check_constraint(op.f("ck_side_quests_category"), "side_quests", f"category IS NULL OR category IN {OLD}")
