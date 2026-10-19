import { type ThemeId, useTheme } from "../../lib/theme";

/**
 * Chart colors per theme, each set validated against its card surface with the dataviz validator
 * (scripts/validate_palette.js, all checks pass). Categorical slots keep this fixed order; never cycle.
 * - minimal: the reference palette's dark column on #111113
 * - modern: violet / coral / cyan lead (slot 8 orchid: red sat too close to green for deutans), dark mode on the glass card (~#151729)
 * - zen: Japanese earth tones (ai, kaki, wakatake, yamabuki, ume, moegi, fuji, bengara), light mode on paper #fbf8f1
 */
type ChartColors = {
  series: readonly string[];
  ink: { primary: string; secondary: string; muted: string; grid: string };
  /** Behind the marks: the 2px gap ring around dots and between stacked bars */
  surface: string;
  tooltip: string;
  cursor: string;
};

const CHART_COLORS: Record<ThemeId, ChartColors> = {
  minimal: {
    series: ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"],
    ink: { primary: "#f4f4f5", secondary: "#a1a1aa", muted: "#71717a", grid: "#27272a" },
    surface: "#111113",
    tooltip: "#18181b",
    cursor: "rgba(255,255,255,0.04)",
  },
  modern: {
    series: ["#8f7cf0", "#e8655a", "#1597b3", "#c98500", "#d55181", "#3f8be8", "#3a9a3a", "#c75bb8"],
    ink: { primary: "#eef0fa", secondary: "#a3a7c2", muted: "#7f84a3", grid: "#262a45" },
    surface: "#151729",
    tooltip: "#181a2e",
    cursor: "rgba(196,204,255,0.06)",
  },
  zen: {
    series: ["#3a6ea5", "#c95f2c", "#1f9470", "#b07d00", "#c45c87", "#5f8a1f", "#7461b8", "#b8433f"],
    ink: { primary: "#2e2823", secondary: "#6b6152", muted: "#786d5c", grid: "#e8e0d0" },
    surface: "#fbf8f1",
    tooltip: "#fffdf8",
    cursor: "rgba(46,40,35,0.05)",
  },
};

export const useChartColors = (): ChartColors => CHART_COLORS[useTheme()];

/** Muscle groups in a fixed order so each group keeps its color in every chart. */
export const MUSCLE_GROUPS = [
  ["chest", "Hrudník"],
  ["back", "Záda"],
  ["legs", "Nohy"],
  ["shoulders", "Ramena"],
  ["biceps", "Biceps"],
  ["triceps", "Triceps"],
  ["core", "Core"],
  ["full_body", "Celé tělo"],
] as const;
