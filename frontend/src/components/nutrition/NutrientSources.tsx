import { useState } from "react";
import type { NutrientTotal } from "../../api/nutrition";
import { formatNumber } from "../../lib/format";
import { Sheet } from "../ui";

const POPOVER_ROWS = 8;

const digits = (value: number, unit: string) => (unit === "kcal" || value >= 100 ? 0 : value >= 1 ? 1 : 2);

// Devices with a real pointer get a hover tooltip; a tap (any device) opens the full list in a sheet
const canHover = () => typeof window !== "undefined" && window.matchMedia("(hover: hover) and (pointer: fine)").matches;

function SourceList({ nutrient, limit }: { nutrient: NutrientTotal; limit?: number }) {
  const sources = nutrient.sources ?? [];
  const unknown = nutrient.unknown ?? [];
  const total = sources.reduce((sum, s) => sum + s.amount, 0);
  const shown = limit ? sources.slice(0, limit) : sources;
  const rest = sources.length - shown.length;
  if (sources.length === 0 && unknown.length === 0) return <p className="text-zinc-500">Dnes nic zapsaného.</p>;
  return (
    <div className="space-y-2">
      {shown.length > 0 && (
        <ul className="space-y-1">
          {shown.map((source) => (
            <li key={source.name} className="flex items-baseline justify-between gap-3">
              <span className="min-w-0 flex-1 text-zinc-300">{source.name}</span>
              <span className="whitespace-nowrap tabular-nums text-zinc-200">
                {source.estimated && <span className="text-zinc-500">≈ </span>}
                {formatNumber(source.amount, digits(source.amount, nutrient.unit))} {nutrient.unit}
                <span className="text-zinc-500"> · {formatNumber(total > 0 ? (source.amount / total) * 100 : 0)} %</span>
              </span>
            </li>
          ))}
        </ul>
      )}
      {rest > 0 && <p className="text-xs text-zinc-500">a {rest} další (klepni pro celý seznam)</p>}
      {sources.some((s) => s.estimated) && <p className="text-xs text-zinc-500">≈ odhad z USDA podle surovin potraviny</p>}
      {unknown.length > 0 && <p className="text-xs text-zinc-500">Bez údaje: {unknown.join(", ")}</p>}
    </div>
  );
}

/** Wraps a nutrient tile: hover shows which foods it came from, a tap opens the whole breakdown. */
export function NutrientSources({
  nutrient,
  children,
  align = "left",
  className = "",
}: {
  nutrient: NutrientTotal;
  children: React.ReactNode;
  align?: "left" | "right";
  className?: string;
}) {
  const [hovered, setHovered] = useState(false);
  const [sheet, setSheet] = useState(false);
  const hover = canHover();
  return (
    <div
      className={`relative ${className}`}
      onMouseEnter={hover ? () => setHovered(true) : undefined}
      onMouseLeave={hover ? () => setHovered(false) : undefined}
    >
      <button
        type="button"
        onClick={() => {
          setHovered(false);
          setSheet(true);
        }}
        aria-label={`${nutrient.label}: z čeho to je`}
        className="block w-full cursor-pointer text-left"
      >
        {children}
      </button>
      {hovered && !sheet && (
        <div
          role="tooltip"
          className={`absolute top-full z-30 mt-1 w-80 max-w-[calc(100vw-2rem)] rounded-xl border border-zinc-700 bg-zinc-900 p-3 text-sm shadow-xl ${
            align === "right" ? "right-0" : "left-0"
          }`}
        >
          <p className="mb-2 font-medium">{nutrient.label}</p>
          <SourceList nutrient={nutrient} limit={POPOVER_ROWS} />
        </div>
      )}
      {sheet && (
        <Sheet title={nutrient.label} onClose={() => setSheet(false)}>
          <p className="mb-3 text-sm text-zinc-400">
            Celkem {formatNumber(nutrient.amount, digits(nutrient.amount ?? 0, nutrient.unit))} {nutrient.unit}
            {nutrient.percent !== null && ` · ${formatNumber(nutrient.percent)} % cíle`}
          </p>
          <SourceList nutrient={nutrient} />
        </Sheet>
      )}
    </div>
  );
}
