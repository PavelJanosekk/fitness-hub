import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { ChevronLeft } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { type BucketBoard, type BucketItem, useBucketBoard, useSetCountry } from "../api/bucket";
import { CountryPicker, saveError } from "../components/bucket/ItemForm";
import { useChartColors } from "../components/charts/palette";
import { Card } from "../components/Layout";
import { Button, Segmented, Sheet } from "../components/ui";
import { countryName, fullDate, RARITY } from "../lib/bucket";
import { useTheme } from "../lib/theme";

const VIEWS = [
  ["world", "Svět"],
  ["trips", "Výpravy"],
] as const;

type Feature = { type: "Feature"; properties: { c: string; k: string }; geometry: GeoJSON.MultiPolygon };
type World = { type: "FeatureCollection"; features: Feature[] };

const TILE_FILTER = {
  minimal: "invert(1) hue-rotate(180deg) brightness(0.9) contrast(0.9) saturate(0.6)",
  modern: "invert(1) hue-rotate(200deg) brightness(0.85) contrast(0.9) saturate(0.7)",
  zen: "sepia(0.25) saturate(0.8)",
} as const;
const HOME: [number, number] = [49.4875, 16.66]; // Boskovice

/** A theme colour (themes remap the Tailwind palette variables). */
const cssColor = (name: string, fallback: string) => getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
const accent = () => cssColor("--color-emerald-500", "#10b981");

/** Bucket list maps (E36): a scratch map of the world (tap a country to mark it) and the trips with coordinates. */
export function BucketMap() {
  const board = useBucketBoard();
  const [params, setParams] = useSearchParams();
  const view = params.get("v") === "trips" ? "trips" : "world";
  if (!board.data) return <p className="text-zinc-500">{board.isPending ? "Načítám…" : "Mapu se nepodařilo načíst."}</p>;
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <Link to="/hero/bucket" className="flex items-center gap-1 py-2 pr-2 text-sm text-zinc-400">
          <ChevronLeft size={18} /> Bucket list
        </Link>
        <Segmented options={VIEWS} value={view} onChange={(v) => setParams(v === "trips" ? { v } : {}, { replace: true })} />
      </div>
      {view === "world" ? <WorldView board={board.data} /> : <TripsView board={board.data} />}
    </div>
  );
}

function WorldView({ board }: { board: BucketBoard }) {
  const [world, setWorld] = useState<World | null>(null);
  const [failed, setFailed] = useState(false);
  const [picked, setPicked] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const setCountry = useSetCountry();
  useEffect(() => {
    fetch("/world-110m.json")
      .then((r) => r.json())
      .then(setWorld)
      .catch(() => setFailed(true));
  }, []);

  const visited = useMemo(() => new Map(board.countries.map((c) => [c.code, c])), [board.countries]);
  const wished = useMemo(() => new Set(board.items.filter((i) => !i.done).flatMap((i) => i.country_codes)), [board.items]);
  const continents = Object.keys(board.continents);

  return (
    <>
      <Card className="space-y-3">
        <div className="flex items-end justify-between">
          <div>
            <div className="text-3xl font-bold tabular-nums">{visited.size}</div>
            <div className="text-[13px] text-zinc-400">{visited.size === 1 ? "země" : visited.size < 5 ? "země" : "zemí"} na mapě</div>
          </div>
          <div className="text-right">
            <div className="text-3xl font-bold tabular-nums">{continents.length} / 7</div>
            <div className="text-[13px] text-zinc-400">kontinentů</div>
          </div>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {Object.entries(board.continent_names).map(([key, name]) => (
            <span key={key} className={`rounded-full px-2.5 py-1 text-xs ${key in board.continents ? "bg-emerald-500/15 text-emerald-300" : "bg-zinc-800 text-zinc-500"}`}>
              {name}
            </span>
          ))}
        </div>
      </Card>

      {failed ? (
        <Card>
          <p className="text-zinc-400">Mapu světa se nepodařilo načíst.</p>
        </Card>
      ) : world ? (
        <WorldMap world={world} visited={visited} wished={wished} onPick={setPicked} />
      ) : (
        <div className="h-72 animate-pulse rounded-xl bg-zinc-900" />
      )}
      <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-zinc-400">
        <Legend className="bg-emerald-500" label="navštíveno" />
        <Legend className="bg-amber-400/60" label="na bucket listu" />
        <span>Ťukni na zemi a označ ji.</span>
      </p>

      <Button variant="ghost" className="w-full" onClick={() => setAdding(true)}>
        Přidat zemi ze seznamu (i malé státy)
      </Button>

      <section className="space-y-2">
        <h2 className="px-0.5 pt-1 font-semibold">Navštívené země</h2>
        <div className="ui-card divide-y divide-zinc-800 overflow-hidden">
          {[...visited.values()]
            .sort((a, b) => countryName(a.code).localeCompare(countryName(b.code), "cs"))
            .map((c) => (
              <button key={c.code} onClick={() => setPicked(c.code)} className="flex min-h-12 w-full items-center justify-between gap-3 px-3 py-2 text-left active:bg-zinc-800/60">
                <span>
                  <span className="block text-[15px]">{countryName(c.code)}</span>
                  <span className="text-xs text-zinc-500">
                    {[c.continent && board.continent_names[c.continent], c.visited_on ? fullDate(c.visited_on) : "před aplikací", ...c.items].filter(Boolean).join(" · ")}
                  </span>
                </span>
              </button>
            ))}
        </div>
      </section>

      {picked && <CountrySheet board={board} code={picked} onClose={() => setPicked(null)} />}
      {adding && (
        <Sheet title="Přidat zemi" onClose={() => setAdding(false)}>
          <CountryPicker
            board={board}
            value={[...visited.keys()]}
            onChange={(codes) => {
              const added = codes.find((c) => !visited.has(c));
              if (added) setCountry.mutate({ code: added, visited: true }, { onSuccess: () => setAdding(false) });
            }}
          />
          {setCountry.isError && <p className="mt-2 text-sm text-red-300">{saveError(setCountry.error)}</p>}
        </Sheet>
      )}
    </>
  );
}

function Legend({ className, label }: { className: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className={`size-3 rounded-sm ${className}`} /> {label}
    </span>
  );
}

function WorldMap({
  world,
  visited,
  wished,
  onPick,
}: {
  world: World;
  visited: Map<string, unknown>;
  wished: Set<string>;
  onPick: (code: string) => void;
}) {
  const colors = useChartColors();
  const element = useRef<HTMLDivElement>(null);
  const pick = useRef(onPick);
  pick.current = onPick;

  useEffect(() => {
    if (!element.current) return;
    const m = L.map(element.current, {
      zoomSnap: 0.25,
      minZoom: 0.75,
      maxZoom: 6,
      worldCopyJump: false,
      maxBounds: [
        [-75, -200],
        [85, 200],
      ],
      attributionControl: true,
    });
    m.attributionControl.setPrefix(false);
    m.attributionControl.addAttribution("Natural Earth");
    const fill = accent();
    const land = cssColor("--color-zinc-700", colors.ink.grid);
    L.geoJSON(world as GeoJSON.FeatureCollection, {
      style: (feature) => {
        const code = (feature as Feature).properties.c;
        const isVisited = visited.has(code);
        return {
          color: colors.surface,
          weight: 0.6,
          fillColor: isVisited ? fill : wished.has(code) ? colors.series[3] : land,
          fillOpacity: isVisited ? 0.95 : wished.has(code) ? 0.55 : 1,
        };
      },
      onEachFeature: (feature, layer) => layer.on("click", () => pick.current((feature as Feature).properties.c)),
    }).addTo(m);
    m.fitBounds(
      [
        [-50, -165],
        [75, 175],
      ],
      { padding: [0, 0] },
    );
    return () => void m.remove();
  }, [world, visited, wished, colors]);

  // Inline background: leaflet.css paints the container light grey
  return (
    <div
      ref={element}
      className="isolate h-72 overflow-hidden rounded-xl"
      style={{ background: "var(--color-zinc-900)" }}
      role="img"
      aria-label="Mapa světa s navštívenými zeměmi"
    />
  );
}

function CountrySheet({ board, code, onClose }: { board: BucketBoard; code: string; onClose: () => void }) {
  const setCountry = useSetCountry();
  const country = board.countries.find((c) => c.code === code);
  const open = board.items.filter((i) => !i.done && i.country_codes.includes(code));
  const continent = board.country_continents[code];
  return (
    <Sheet title={countryName(code)} onClose={onClose}>
      <div className="space-y-3">
        <p className="text-sm text-zinc-400">
          {continent ? board.continent_names[continent] : ""}
          {country && ` · navštíveno ${country.visited_on ? fullDate(country.visited_on) : "před aplikací"}`}
        </p>
        {country && country.items.length > 0 && <p className="text-sm">Z bucket listu: {country.items.join(", ")}</p>}
        {open.length > 0 && <p className="text-sm text-amber-300">Na bucket listu: {open.map((i) => i.title).join(", ")}</p>}
        {setCountry.isError && <p className="text-sm text-red-300">{saveError(setCountry.error)}</p>}
        {!country ? (
          <div className="grid grid-cols-2 gap-2">
            <Button variant="ghost" disabled={setCountry.isPending} onClick={() => setCountry.mutate({ code, visited: true, visited_on: null }, { onSuccess: onClose })}>
              Byl jsem dřív
            </Button>
            <Button disabled={setCountry.isPending} onClick={() => setCountry.mutate({ code, visited: true }, { onSuccess: onClose })}>
              Jsem tu teď
            </Button>
          </div>
        ) : country.on_map ? (
          <Button variant="danger" className="w-full" disabled={setCountry.isPending} onClick={() => setCountry.mutate({ code, visited: false }, { onSuccess: onClose })}>
            Odebrat z mapy
          </Button>
        ) : (
          <p className="text-xs text-zinc-500">Na mapě je díky splněné položce; odebereš ji zrušením splnění.</p>
        )}
        <p className="text-xs text-zinc-500">„Byl jsem dřív“ se počítá jen do mapy a odznaků, „Jsem tu teď“ dostane dnešní datum.</p>
      </div>
    </Sheet>
  );
}

function TripsView({ board }: { board: BucketBoard }) {
  const theme = useTheme();
  const colors = useChartColors();
  const navigate = useNavigate();
  const element = useRef<HTMLDivElement>(null);
  const trips = useMemo(
    () => board.items.filter((i): i is BucketItem & { lat: number; lon: number } => i.lat != null && i.lon != null),
    [board.items],
  );

  useEffect(() => {
    if (!element.current || !trips.length) return;
    const m = L.map(element.current, { scrollWheelZoom: false, zoomSnap: 0.25 });
    m.attributionControl.setPrefix(false);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 18,
      attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    }).addTo(m);
    const rarity = [
      cssColor("--color-zinc-500", colors.ink.muted),
      cssColor("--color-sky-500", colors.series[0]),
      cssColor("--color-violet-500", "#8b5cf6"),
      cssColor("--color-amber-400", colors.series[3]),
    ];
    L.circleMarker(HOME, { radius: 5, color: colors.surface, weight: 2, fillColor: colors.ink.primary, fillOpacity: 1 })
      .bindTooltip("Domov")
      .addTo(m);
    const markers = trips.map((t) =>
      L.circleMarker([t.lat, t.lon], {
        radius: 9,
        color: t.done ? accent() : colors.surface,
        weight: t.done ? 3 : 2,
        fillColor: rarity[t.rarity - 1],
        fillOpacity: t.done ? 0.45 : 0.95,
      })
        .bindTooltip(t.title)
        .on("click", () => navigate(`/hero/bucket?i=${t.id}`))
        .addTo(m),
    );
    m.fitBounds(L.featureGroup(markers).getBounds().extend(HOME), { padding: [24, 24] });
    return () => void m.remove();
  }, [trips, colors, navigate]);

  if (!trips.length) {
    return (
      <Card>
        <p className="text-zinc-400">Žádná položka zatím nemá souřadnice.</p>
      </Card>
    );
  }
  return (
    <>
      <div
        ref={element}
        className="isolate h-96 overflow-hidden rounded-xl bg-zinc-900 [&_.leaflet-tile-pane]:[filter:var(--tile-filter)]"
        style={{ "--tile-filter": TILE_FILTER[theme] } as React.CSSProperties}
        role="img"
        aria-label="Mapa výprav"
      />
      <div className="ui-card divide-y divide-zinc-800 overflow-hidden">
        {[...trips]
          .sort((a, b) => Number(a.done) - Number(b.done) || (a.travel_time ?? "~").localeCompare(b.travel_time ?? "~"))
          .map((t) => (
            <Link key={t.id} to={`/hero/bucket?i=${t.id}`} className="flex min-h-12 items-center gap-3 px-3 active:bg-zinc-800/60">
              <span className={`size-3 shrink-0 rounded-full ${RARITY[t.rarity].bar} ${t.done ? "opacity-40" : ""}`} />
              <span className={`flex-1 text-[15px] ${t.done ? "text-zinc-400" : ""}`}>{t.title}</span>
              <span className="text-xs text-zinc-500">{t.done ? "splněno" : (t.travel_time ?? "")}</span>
            </Link>
          ))}
      </div>
    </>
  );
}
