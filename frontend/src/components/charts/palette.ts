/**
 * Chart colors: the dataviz reference palette, dark column, validated against the card surface #111113
 * (scripts/validate_palette.js, all checks pass). Categorical slots keep this fixed order; never cycle.
 */
export const SERIES = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9"] as const;

export const INK = { primary: "#f4f4f5", secondary: "#a1a1aa", muted: "#71717a", grid: "#27272a" } as const;

/** Muscle groups in a fixed order so each group keeps its color in every chart. */
export const MUSCLE_GROUPS = [
  ["chest", "Hrudník"],
  ["back", "Záda"],
  ["legs", "Nohy"],
  ["shoulders", "Ramena"],
  ["arms", "Paže"],
  ["core", "Core"],
  ["full_body", "Celé tělo"],
] as const;
