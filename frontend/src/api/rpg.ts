import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";

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
};
export type XpEntry = { amount: number; kind: string; text: string };
export type XpDay = { date: string; total: number; entries: XpEntry[] };
export type Pause = { id: number; start_date: string; end_date: string | null; note: string | null };

export const rpgKeys = {
  character: ["rpg", "character", "v1"] as const,
  history: (days: number) => ["rpg", "history", "v1", days] as const,
  pauses: ["rpg", "pauses", "v1"] as const,
};

// The ledger is computed from everything (habits, gym, runs, food), so it is always refetched when shown
export const useCharacter = () =>
  useQuery({ queryKey: rpgKeys.character, queryFn: () => api<Character>("/api/rpg/character"), staleTime: 0 });
export const useXpHistory = (days: number) =>
  useQuery({ queryKey: rpgKeys.history(days), queryFn: () => api<XpDay[]>(`/api/rpg/history?days=${days}`), staleTime: 0 });
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
