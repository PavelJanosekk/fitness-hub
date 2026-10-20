# Zadání pro coding agenta: Progressive Overload a doporučování tréninku

> **Status:** original spec provided by the user on 2026-10-20 (in Czech), saved verbatim (only Markdown
> headings and lists restored). Not accepted as-is: the critique, the mapping onto the current data model and the
> decisions it needs are in `docs/overload-spec-review-2026-10-20.md`. It revises the first version of the
> targets (E33, `docs/PROGRESS.md`), which was built on dev but not deployed.

## 1. Cíl

Rozšiř existující aplikaci pro logování silově-hypertrofického tréninku o systém, který uživateli doporučuje cílovou váhu a počet opakování pro následující trénink na základě jeho skutečné tréninkové historie.

Nejde o generátor univerzálního tréninkového plánu. Aplikace už eviduje tréninky, cviky, série, váhy a opakování. Nová funkcionalita má tuto historii využít k tomu, aby byl progresivní overload srozumitelný, praktický a dlouhodobě udržitelný.

Před implementací nejprve prozkoumej existující aplikaci, používané vzory, UX, pojmenování a způsob práce s tréninky. Navrhni a implementuj řešení, které přirozeně zapadne do současné architektury. Nepřepisuj nesouvisející části aplikace. Konkrétní technické řešení, interní reprezentaci dat a změny persistence zvol podle skutečného stavu projektu.

## 2. Základní principy

- Doporučení jsou vodítko pro další trénink, ne povinnost ani záruka, že uživatel daný výkon zvládne.
- Zachovej historii skutečně odcvičených tréninků. Změna algoritmu nesmí zpětně upravovat historické výkony.
- Uživatel smí kdykoliv změnit doporučenou váhu, počet opakování nebo plán série. Ruční úprava nesmí být považována za chybu.
- Progres vyhodnocuj primárně na úrovni konkrétního cviku a jeho srovnatelných tréninkových expozic.
- Nevyvozuj přesné fyziologické závěry z nepřesných údajů. RIR, odhadované 1RM a změny výkonu jsou pomocné signály, nikoliv absolutní pravda.
- Upřednostňuj předvídatelná, vysvětlitelná a testovatelná pravidla před složitým algoritmem, který uživateli nedokáže vysvětlit své rozhodnutí.
- Jednorázový slabší trénink automaticky neznamená, že je váha špatná nebo že je nutný deload.
- Systém má podporovat postupný dlouhodobý progres a vhodnou míru úsilí, nikoliv nutit uživatele překonávat rekord v každém cviku při každém tréninku.

## 3. Nastavení cviku a progresní strategie

V rámci stávajícího způsobu konfigurace cviků/šablon umožni nastavit nebo odvodit tyto koncepty:

- Počet pracovních sérií podle existující šablony. Systém jej při běžném progresu automaticky nemění.
- Rozsah opakování: dolní a horní hranice, například 6–10.
- Minimální váhový krok pro daný cvik nebo vybavení, například nejmenší dostupné navýšení na stroji či čince.
- Cílová rezerva opakování (RIR) pro cvik. Výchozí hodnota může být 1 RIR, ale musí být možné ji změnit, včetně cíleného tréninku do selhání.
- Progresní strategie:
  - Straight sets: pracovní série jsou plánované se stejnou váhou.
  - Top-set + back-off: první/hlavní série má samostatný cíl a další série jsou plánované s nižší zátěží.
- U plánovaných top-setů a back-off sérií musí být zřejmé, jakou mají roli. Algoritmus nesmí tuto strukturu odhadovat pouze podle toho, že se v jednom tréninku objevily různé váhy.

Pokud současný produkt používá jiný koncept šablon nebo cviků, přizpůsob tato nastavení jeho existujícímu modelu namísto zavádění paralelního systému.

## 4. RIR a interpretace úsilí

RIR (reps in reserve) je odhad počtu dalších technicky čistých opakování, která by uživatel zvládl. Hodnota může být nepřesná, zejména u delších sérií a u méně zkušeného uživatele.

Požadované chování

- U každé série lze rychle zaznamenat RIR, například 0, 1, 2, 3+.
- Logování běžné série musí zůstat rychlé: RIR nesmí vyžadovat další povinný krok.
- Rozlišuj mezi RIR, který uživatel výslovně potvrdil, a výchozí/předpokládanou hodnotou použitou bez interakce. Pokud aplikace použije výchozí RIR, nesmí ho prezentovat jako uživatelem potvrzenou fyziologickou skutečnost.
- RIR nesmí být automaticky převáděno na „efektivní opakování“ prostým vzorcem opakování + RIR a používáno jako přesná ekvivalence.
- Skutečný počet dokončených opakování je vždy samostatně zachován. RIR slouží k interpretaci náročnosti série, porovnávání podobných výkonů a kontextu doporučení.
- Pokud je RIR neznámé, nepřesné nebo pouze předvyplněné, algoritmus musí být stále schopen vytvořit rozumné doporučení na základě opakování, váhy a historie.
- Cílový RIR ovlivňuje očekávané úsilí, ale systém nesmí uživatele nutit do selhání u každé série.

## 5. Určení, zda lze výkony porovnávat

Před vyhodnocením progrese zkontroluj, zda je poslední trénink daného cviku dostatečně srovnatelný s předchozími.

Za okolnosti, které mohou srovnatelnost snížit, považuj zejména:

- změnu varianty cviku, vybavení nebo nastavení stroje;
- zjevně odlišný rozsah pohybu či techniku, pokud je tato informace dostupná;
- zásadní rozdíl v délce odpočinku, pokud je zaznamenáván;
- neplánovanou změnu vah mezi sériemi;
- uživatelem označený neobvyklý průběh tréninku, bolest, přerušení nebo mimořádnou únavu.

Není nutné všechny tyto údaje povinně vyžadovat při každém tréninku. Pokud kontext chybí, použij konzervativní interpretaci a nepředstírej jistotu. Nesrovnatelný trénink může být užitečný pro historii, ale neměl by bez dalšího spustit automatický trvalý posun váhy.

## 6. Generování cílů pro další trénink

Při vytváření tréninku nabídni pro každou pracovní sérii výchozí cíl váhy a počtu opakování. Cíle vycházejí z posledních srovnatelných tréninků daného cviku, jeho progresní strategie a nastaveného rozsahu opakování.

Každé doporučení musí mít srozumitelný důvod, například:

- +1 opakování;
- Zvýšení váhy;
- Back-off – pokračovat v progresi;
- Návrat na vyšší váhu;
- Udržet cíl;
- Prověřit propad výkonu.

### 6.1 Straight sets

U cviku, kde mají všechny pracovní série stejnou plánovanou váhu, použij tato výchozí pravidla:

Zvýšení váhy je možné doporučit, pokud:

1. první pracovní série dosáhla horní hranice rozsahu opakování;
2. prostřední pracovní série (pokud existuje) dosáhly alespoň dolní hranice rozsahu;
3. poslední pracovní série zůstala nejvýše jedno opakování pod dolní hranicí rozsahu;
4. poslední trénink byl dostatečně srovnatelný a není označený jako neobvyklý výkyv.

Pravidla musí fungovat i u cviků s jiným počtem sérií než tři. U dvou sérií se posuzuje první a poslední série; u více sérií se kontrolují všechny prostřední série.

Příklad pro rozsah 6–10 a tři série: výkon 10, 8, 6 je kandidátem na navýšení váhy. Výkon 10, 7, 5 může navýšení také splnit, protože poslední série je o jedno opakování pod dolní hranicí. Výkon 10, 5, 4 podmínky nesplňuje.

Jde o výchozí, srozumitelnou strategii aplikace, nikoliv o univerzální fyziologické pravidlo. Udrž ji konzistentní a umožni ji později upravit bez přepisování historie.

Pokud podmínka pro navýšení váhy není splněna:

- Pokud první série ještě nedosáhla horní hranice, prioritně navrhni posun první série o jedno opakování, pokud uživatel minule zvládl svůj cíl. Ostatní cíle obvykle ponech.
- Pokud první série už dosáhla horní hranice, ale některá pozdější série je slabá, prioritně posuň první pozdější sérii, která nesplňuje požadovanou hranici. První sérii nenuť nad horní hranici rozsahu.
- Pokud uživatel předchozí cíl nesplnil, automaticky nepřidávej další opakování jen proto, že algoritmus chce progres. Podle rozsahu odchylky a dosavadní historie cíl zopakuj, konzervativně uprav nebo označ výkon k přezkoumání.
- Cíle dalších sérií neměň bez důvodu. Uživatel má být schopen pochopit, která série je aktuálně prioritou pro progres.

### 6.2 Odhad cíle po zvýšení váhy

Po zvýšení zátěže odvoď počáteční cíl opakování z posledních srovnatelných výkonů, velikosti váhového skoku a typické únavové křivky daného cviku.

- Nepoužívej jeden univerzální převod 1RM jako přesnou předpověď opakování pro každou sérii.
- Zachovej individuální rozdíl mezi první a dalšími sériemi.
- Odhad 1RM lze používat jako podpůrný trend u stejného cviku, ne jako přesnou metriku srovnávající různé cviky.
- Pokud je váhový skok relativně velký a předpokládaný výkon by klesl výrazně pod rozsah, zvaž menší dostupný krok nebo upozorni, že skok může být příliš velký.
- Výpočet představuje startovní cíl. Skutečný výkon při příští expozici rozhodne, jak se doporučení upraví dále.

Příklad: pokud uživatel zvládl 40 kg × 10, 8, 6, může aplikace po navýšení na 42,5 kg odhadnout například 8, 6, 5. Tato konkrétní čísla jsou ilustrativní, nikoliv pevný vzorec.

### 6.3 Propad výkonu a Auto-Drop

Nesnižuj trvale váhu konkrétní série automaticky jen proto, že v jednom tréninku spadla pod dolní hranici rozsahu.

- Jednorázový výrazný propad označ jako problémový výkon a případně nabídni nižší váhu jako možnost.
- Automatické doporučení nižší váhy je vhodnější po opakovaném propadu ve srovnatelných podmínkách nebo po výslovném potvrzení uživatelem, že zátěž byla příliš vysoká.
- Rozlišuj mezi doporučením pro příští trénink a přepsáním dlouhodobého plánu. Jednorázový výkyv nesmí bezdůvodně změnit strukturu dalších tréninků.
- Pokud je výkon výrazně horší než obvykle, zvaž jako možné vysvětlení únavu, nedostatečný odpočinek, odlišný průběh tréninku nebo chybu v logování. Automaticky neurčuj jedinou příčinu.

### 6.4 Top-set a back-off série

Pokud je top-set a back-off struktura součástí plánované strategie cviku:

- První hlavní série a back-off série mohou mít rozdílné cíle a postupují nezávisle podle své role.
- Když se zvýší váha top-setu, neznamená to automaticky zvýšení váhy všech back-off sérií.
- Back-off sérii lze posunout na vyšší váhu, když tato konkrétní série dosáhne horní hranice rozsahu a jsou splněny podmínky její strategie. Po zvýšení vytvoř konzervativní odhad opakování.
- Více back-off sérií může postupovat nezávisle, pokud je takový postup slučitelný s plánem cviku.
- Když uživatel ručně změní váhu jen během aktuálního tréninku, neinterpretuj tuto změnu automaticky jako trvalou změnu progresní strategie.

Příklad: při plánovaném 30 kg top-setu a 25 kg back-off sériích mohou back-off série zůstat na 25 kg, i když top-set přejde na vyšší váhu.

### 6.5 Neplánovaná ruční změna zátěže

Uživatel může během cviku zjistit, že si vybral špatnou váhu, a opravit ji.

- Pokud uživatel změní váhu u straight sets, automaticky nabídni propsání stejné váhy do následujících dosud nezačatých sérií daného bloku. Změna musí být snadno vratná.
- Nepřepisuj série, které už uživatel dokončil.
- Nepřepisuj plánované série s jinou rolí nebo jinou explicitně nastavenou vahou, například plánovaný back-off.
- Ruční změna platí pro aktuální trénink. Pro příští trénink ji aplikuj pouze tehdy, pokud ji uživatel výslovně potvrdí nebo pokud ji algoritmus vyhodnotí jako součást opakovaného a srovnatelného vzorce.
- Při výpočtu příštího doporučení rozlišuj mezi plánovaným back-offem a jednorázovou opravou váhy.

## 7. Únava mezi cviky stejné svalové partie

Cviky na stejnou svalovou partii se mohou vzájemně ovlivnit, ale velikost tohoto vlivu nelze přesně odvodit pouze z toho, že na předchozím cviku padlo PR.

Požadované chování

- Nesnižuj automaticky cíle dalšího cviku pouze proto, že první cvik zaznamenal PR. Samotné PR není spolehlivým měřítkem aktuální únavy.
- Pokud uživatel na předchozím cviku provedl nezvykle náročný výkon nebo výrazně změnil zátěž/objem a další cvik poté zaznamenal propad, označ tento výkon jako potenciálně ovlivněný únavou.
- Zachovej cíl dalšího cviku, dokud není důvod ho měnit. Můžeš zobrazit nenásilné upozornění, že dnešní výkon může být ovlivněn předchozím cvikem.
- Nabídni uživateli možnost pro daný trénink zvolit Udržet cíl nebo použít konzervativnější cíl. Taková volba nesmí bez potvrzení měnit budoucí plán.
- Jednorázový propad na druhém cviku nesmí okamžitě spustit Auto-Drop.
- Při dalším doporučení vycházej zejména z historie samotného cviku a z více srovnatelných expozic. Nezvyšuj cíl automaticky jen s předpokladem, že se tělo příště adaptuje na únavu.

## 8. Souhrnný přehled svalové partie

Umožni uživateli sledovat, jak se vyvíjí výkon u cviků přiřazených ke stejné svalové partii, ale neslučuj odhadované 1RM z různých cviků do jednoho čísla, které by se prezentovalo jako přesná metrika partie.

- Každý cvik má vlastní trend výkonu.
- Přehled partie shrnuje, které cviky se zlepšují, zůstávají stabilní nebo opakovaně klesají.
- Pokud se jeden cvik zlepší a ostatní zůstanou stabilní, lze shrnout, že výkonnostní trend partie je pozitivní. Netvrď, že to přímo dokazuje růst svalové hmoty.
- Pokud se zlepší jeden cvik a jiný se zhorší, ukaž obě informace. Neoznačuj situaci automaticky za kompenzaci bez jasných dat.
- PR v jednom cviku je pozitivní signál, ale nepředstavuje univerzální důkaz, že všechny cviky nebo celá svalová partie progresují.
- Pro souhrnné hodnocení preferuj trendy z více srovnatelných expozic před verdiktem založeným na jediném tréninku.

V UI používej přesné formulace jako výkon se zlepšuje, stabilní, opakovaný pokles nebo nedostatek srovnatelných dat. Vyhni se nepodloženým tvrzením typu svalová partie určitě roste.

## 9. Stagnace a deload

Tři tréninky bez nového PR samy o sobě nestačí k automatickému deloadu.

- Po několika srovnatelných expozicích bez pozitivního trendu může aplikace upozornit na možné zpomalení progresu.
- Rozlišuj mezi stabilním výkonem a opakovaným poklesem výkonu.
- Při posuzování stagnace zvaž více cviků, úsilí/RIR, kontext tréninku a případné informace o únavě, pokud jsou k dispozici.
- Deload doporuč jako možnost k potvrzení uživatelem, ne jako automatickou změnu programu.
- Pokud je deload doporučen, nabídni srozumitelnou možnost dočasně snížit zátěž, počet sérií nebo obojí. Konkrétní úpravu zobraz jako návrh, který lze potvrdit a upravit.
- Nedoporučuj deload pouze proto, že pokročilý uživatel několik tréninků nezaznamenal rekord.

## 10. Uživatelské rozhraní

### 10.1 Logování sérií bez zbytečných kroků

- U každé série zobraz doporučenou váhu a počet opakování předvyplněné jako výchozí cíl.
- Dokončení série musí vyžadovat co nejméně interakcí.
- RIR lze změnit jedním rychlým ovládacím prvkem, například 0, 1, 2, 3+.
- Výchozí hodnota nesmí být vizuálně prezentována jako uživatelem potvrzená, pokud ji uživatel nezadal.
- Po dokončení série musí být zřejmé, co bylo doporučeno a co uživatel skutečně provedl.

### 10.2 Vysvětlení doporučení

U cviku nebo jednotlivé série zobraz krátký štítek s důvodem aktuálního cíle. Používej jednoduché a konzistentní názvy, například:

- +1 opakování – prioritní série pro progres;
- Zvýšení váhy – splněny podmínky pro vyšší zátěž;
- Back-off progres – pokračování samostatné progrese back-off série;
- Návrat na vyšší váhu – série dosáhla stanovených podmínek pro posun z back-off úrovně;
- Udržet cíl – opakovat současný cíl;
- Prověřit propad – výkon výrazně zaostal a je třeba zohlednit kontext.

Štítek musí vysvětlovat důvod, nikoliv pouze přidávat barvu. Barvy mohou pomoci s orientací, ale význam musí být srozumitelný i bez nich.

### 10.3 Změna cíle během tréninku

- Uživatel musí mít možnost upravit váhu nebo opakování pro aktuální sérii.
- Pokud změna ovlivňuje následující série, jasně ukaž, které série budou upraveny.
- Změna musí být vratná a nesmí tiše přepsat již dokončené série.
- Neplánovanou změnu pro aktuální trénink nezaměňuj za potvrzenou změnu plánu pro příště.

## 11. Transparentnost a robustnost

- Každé automatické doporučení musí být možné vysvětlit pomocí konkrétních pravidel a nedávné historie cviku.
- Pokud není dostatek srovnatelných dat, použij bezpečný výchozí cíl, například zopakování poslední známé váhy a rozumného počtu opakování, a označ nízkou jistotu doporučení.
- Nenech jeden chybný záznam, jednorázový propad nebo ruční korekci bez vysvětlení přepsat dlouhodobý směr progrese.
- Pokud uživatel změní rozsah opakování, počet sérií nebo progresní strategii, budoucí cíle musí respektovat novou konfiguraci. Historické záznamy zůstávají zachované a nemají být zpětně reinterpretovány tak, aby vypadaly jako původně plánované podle nové konfigurace.
- Výpočet doporučení musí být deterministický: stejná historie, stejná konfigurace a stejná verze pravidel vedou ke stejnému doporučení.
- Připrav testy rozhodovací logiky i hraničních stavů. Testy mají ověřovat chování, ne konkrétní interní implementaci.

## 12. Akceptační scénáře

Považuj funkcionalitu za dokončenou, pokud následující scénáře fungují konzistentně:

1. Běžná progrese: Rozsah 6–10, tři straight sets, výkon 8, 7, 6. Pokud uživatel splnil předchozí cíle, příští cíl prioritně posune první sérii, například na 9, 7, 6.
2. Zvýšení váhy: Rozsah 6–10, výkon 10, 8, 6 za srovnatelných podmínek. Systém doporučí vyšší váhu a konzervativně odhadne opakování pro nové zatížení.
3. Pozdější série omezuje progres: Výkon 10, 5, 5. Systém nezvyšuje váhu; prioritně řeší slabou druhou sérii.
4. Výrazný propad: Výkon 10, 4, 4 v jednom tréninku. Systém označí výsledek k prověření a bez dalšího kontextu trvale nepřepíše plán automatickým Auto-Dropem.
5. Opakovaný propad: Stejný problém nastane i v dalším srovnatelném tréninku. Systém nabídne nebo doporučí konzervativní snížení zátěže podle pravidel cviku.
6. Plánovaný back-off: Série mají plánovanou strukturu 30 kg top-set a 25 kg back-off. Progres top-setu automaticky nepřepíše všechny back-off série.
7. Náhodná úprava váhy: Uživatel ve straight sets sníží váhu u druhé série. Následující nedokončené série aktuálního bloku se mohou propsáním upravit; již dokončené série zůstanou beze změny a příští trénink změnu nepřevezme automaticky jako nový plán.
8. RIR bez potvrzení: Uživatel rychle dokončí sérii bez změny RIR. Logování funguje bez dalších kroků a výchozí RIR se nezamění za výslovně potvrzený odhad.
9. RIR odlišný od cíle: Uživatel splní počet opakování, ale nahlásí jiný RIR. Systém uchová oba údaje a nepočítá je jako přesně ekvivalentní počet opakování.
10. PR na prvním cviku: Chest Press se zlepší, následný Pec Deck má nižší výkon. Cíl Pec Decku se automaticky nesníží pouze kvůli PR; jednorázový propad se vyhodnotí s ohledem na kontext.
11. Přehled partie: Chest Press se zlepšuje a Pec Deck zůstává stabilní. Souhrn ukáže trendy obou cviků a nesloučí jejich odhadované 1RM do údajně přesného skóre partie.
12. Tři tréninky bez PR: Aplikace může upozornit na možné zpomalení progresu, ale automaticky nespustí deload bez dalších signálů a potvrzení uživatelem.
13. Nedostatek dat: Nový nebo výrazně upravený cvik dostane konzervativní výchozí doporučení, aniž by algoritmus předstíral přesnou predikci.
14. Historická konzistence: Změna pravidel nebo konfigurace změní budoucí doporučení, ale nepřepíše dříve zapsanou skutečnost ani již dokončené tréninky.

## 13. Co není cílem

- Automaticky generovat nebo měnit celý tréninkový program.
- Automaticky měnit počet pracovních sérií při běžném progresu.
- Tvrdit, že jedna formule přesně předpoví výkon nebo růst svalů.
- Považovat každý dosažený PR za důkaz mimořádné únavy nebo každou absenci PR za stagnaci.
- Automaticky přepisovat dlouhodobý plán podle jediné ruční změny váhy.
- Předepisovat selhání u každé série jako univerzální podmínku hypertrofie.

## 14. Vědecký kontext a zdroje

Tato funkcionalita má používat jednoduché a vysvětlitelné tréninkové heuristiky. Konkrétní hranice progresu, tolerance poslední série a pravidla upozornění jsou produktová rozhodnutí, nikoliv univerzální pravidla potvrzená studiemi.

Při návrhu a budoucím ladění algoritmu vycházej zejména z těchto zdrojů:

- ACSM, 2026 – aktualizované stanovisko k silovému tréninku: souhrn rozsáhlého souboru přehledů a důkazů o proměnných silového tréninku. PubMed
- Grgic et al., 2022 – trénink do selhání vs. bez selhání: meta-analýza neukazuje univerzální převahu momentálního selhání pro hypertrofii. PubMed
- Deload v silovém a physique tréninku, 2023: práce zdůrazňuje nedostatek přímých důkazů a nejistotu ohledně univerzálního protokolu deloadu. PMC
- Přestávky mezi sériemi a hypertrofie, 2024: výsledky podporují význam dostatečného odpočinku pro zachování výkonu a upozorňují na omezení příliš krátkých pauz. Frontiers
- Přesnost odhadu RIR, 2025: přesnost odhadu rezervy se liší podle podmínek; RIR proto nepovažuj za dokonale přesný měřicí údaj. Taylor & Francis

## 15. Očekávaný postup práce

1. Prozkoumej současnou aplikaci a najdi přirozené místo pro doporučovací logiku i její zobrazení.
2. Stručně identifikuj dotčené části aplikace a případné UX/produktové nejasnosti. Pokud je možné zvolit rozumný výchozí postup bez blokující otázky, pokračuj.
3. Implementuj první ucelenou verzi pro straight sets a plánované top-set/back-off série.
4. Přidej potřebné testy rozhodovací logiky včetně akceptačních scénářů výše.
5. Integruj vysvětlitelné štítky a rychlé ovládání RIR i ručních změn vah podle existujících UI vzorů.
6. Na konci shrň, co bylo změněno, jak fungují hlavní pravidla, jaké testy byly spuštěny a co případně zůstává mimo implementaci.
