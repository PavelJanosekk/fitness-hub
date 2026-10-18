import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";

export type Skill = {
  key: string;
  name: string;
  source: string;
  xp: number;
  level: number;
  level_start_xp: number;
  next_level_xp: number;
  idle_days: number;
  rusting: boolean;
  losing: boolean;
};
export type Character = {
  level: number;
  title: string;
  next_title: { level: number; title: string } | null;
  xp_total: number;
  level_start_xp: number;
  next_level_xp: number;
  today_xp: number;
  week_xp: number;
  multiplier: number;
  week_streak: number;
  forgiven_this_month: string | null;
  paused: boolean;
  skills?: Skill[]; // missing in caches persisted before 7.2
  tired: boolean;
  cursed: string[];
};
export type XpEntry = { amount: number; kind: string; text: string };
export type XpDay = { date: string; total: number; entries: XpEntry[] };
export type Pause = { id: number; start_date: string; end_date: string | null; note: string | null };

export type BossEvent = { date: string; kind: "hit" | "heal"; km: number; text: string };
export type Boss = {
  name: string;
  race_date: string;
  days_left: number;
  max_hp: number;
  hp: number;
  damage_km: number;
  heal_km: number;
  status: "active" | "defeated" | "missed";
  result_seconds: number | null;
  result_km: number | null;
  events: BossEvent[];
};

export type Quest = { key: string; title: string; target: number; unit: string; progress: number; xp: number; done_on: string | null };
export type QuestWeek = { week_start: string; quests: Quest[]; all_bonus_xp: number; all_done: boolean };
export type Badge = { key: string; title: string; description: string; unlocked_on: string | null; progress: string | null };

export const rpgKeys = {
  quests: ["rpg", "quests", "v1"] as const,
  badges: ["rpg", "badges", "v1"] as const,
  boss: ["rpg", "boss", "v1"] as const,
  character: ["rpg", "character", "v2"] as const, // v2: tired + cursed are read without a fallback
  history: (days: number) => ["rpg", "history", "v1", days] as const,
  pauses: ["rpg", "pauses", "v1"] as const,
};

// The ledger is computed from everything (habits, gym, runs, food), so it is always refetched when shown
export const useCharacter = () =>
  useQuery({ queryKey: rpgKeys.character, queryFn: () => api<Character>("/api/rpg/character"), staleTime: 0 });
export const useXpHistory = (days: number) =>
  useQuery({ queryKey: rpgKeys.history(days), queryFn: () => api<XpDay[]>(`/api/rpg/history?days=${days}`), staleTime: 0 });
export const useBoss = () => useQuery({ queryKey: rpgKeys.boss, queryFn: () => api<Boss | null>("/api/rpg/boss"), staleTime: 0 });
export const useQuests = () => useQuery({ queryKey: rpgKeys.quests, queryFn: () => api<QuestWeek>("/api/rpg/quests"), staleTime: 0 });
export const useBadges = () => useQuery({ queryKey: rpgKeys.badges, queryFn: () => api<Badge[]>("/api/rpg/badges") });
export const usePauses = () => useQuery({ queryKey: rpgKeys.pauses, queryFn: () => api<Pause[]>("/api/rpg/pauses") });

/** Start, end or delete a pause. Online only; paused days change streaks, so habits refetch too. */
export function useSavePause() {
  const queryClient = useQueryClient();
  return useMutation({
    retry: 0,
    mutationFn: ({ id, remove, ...body }: { id?: number; remove?: boolean; start_date?: string; end_date?: string | null; note?: string | null }) =>
      remove
        ? api(`/api/rpg/pauses/${id}`, { method: "DELETE" })
        : id
          ? api<Pause>(`/api/rpg/pauses/${id}`, { method: "PATCH", body })
          : api<Pause>("/api/rpg/pauses", { method: "POST", body }),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["rpg"] });
      queryClient.invalidateQueries({ queryKey: ["habits"] });
    },
  });
}
