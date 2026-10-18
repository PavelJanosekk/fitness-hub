import { useSyncExternalStore } from "react";

/**
 * Visual themes, switched in Nastavení → Vzhled and stored per device. The look itself lives in index.css under
 * `<html data-theme>`; index.html applies the saved theme before the first paint (keep KEY and the ids in sync there).
 */
export type ThemeId = "minimal" | "modern" | "zen";

type Theme = {
  id: ThemeId;
  label: string;
  description: string;
  /** Browser / status bar tint (`<meta name="theme-color">`) */
  themeColor: string;
  /** Colors for the small preview in the switcher */
  preview: { page: string; card: string; line: string; ink: string; muted: string; accent: string; font: string };
};

export const THEMES: readonly Theme[] = [
  {
    id: "minimal",
    label: "Minimalistický",
    description: "Tmavý, čistý, nic navíc",
    themeColor: "#09090b",
    preview: { page: "#09090b", card: "#141416", line: "#27272a", ink: "#f4f4f5", muted: "#71717a", accent: "#10b981", font: "inherit" },
  },
  {
    id: "modern",
    label: "Moderní",
    description: "Sklo, polární záře, fialová",
    themeColor: "#06070f",
    preview: {
      page: "radial-gradient(120% 80% at 0% 0%, #4c1d95, transparent 60%), radial-gradient(100% 70% at 100% 30%, #0e7490, transparent 60%), #06070f",
      card: "rgb(255 255 255 / 0.1)",
      line: "rgb(255 255 255 / 0.14)",
      ink: "#eef0fa",
      muted: "#7f84a3",
      accent: "linear-gradient(135deg, #7c5cf2, #4f6ef7)",
      font: 'ui-rounded, "SF Pro Rounded", system-ui, sans-serif',
    },
  },
  {
    id: "zen",
    label: "Zen",
    description: "Papír, dřevo, matcha",
    themeColor: "#efe9dd",
    preview: {
      page: "#efe9dd",
      card: "#fbf8f1",
      line: "#e3dac9",
      ink: "#2e2823",
      muted: "#a89c87",
      accent: "#58744a",
      font: 'ui-serif, "New York", "Iowan Old Style", Georgia, serif',
    },
  },
];

const KEY = "fitness-hub-theme";
const listeners = new Set<() => void>();

const isTheme = (value: unknown): value is ThemeId => THEMES.some((t) => t.id === value);

export const currentTheme = (): ThemeId => {
  const value = document.documentElement.dataset.theme;
  return isTheme(value) ? value : "minimal";
};

export function setTheme(id: ThemeId) {
  try {
    localStorage.setItem(KEY, id);
  } catch {
    // Private mode / blocked storage: the theme still applies until the app is closed
  }
  document.documentElement.dataset.theme = id;
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", THEMES.find((t) => t.id === id)!.themeColor);
  listeners.forEach((l) => l());
}

export function useTheme(): ThemeId {
  return useSyncExternalStore((l) => (listeners.add(l), () => listeners.delete(l)), currentTheme);
}
