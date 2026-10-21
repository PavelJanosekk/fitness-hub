import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";

export type QuestCategory = "learn" | "skill" | "make" | "food" | "move" | "explore" | "people" | "self" | "home" | "trip";
export type QuestDuration = "moment" | "day" | "weekend" | "week" | "month";

export type SideQuest = {
  id: number;
  title: string;
  category: QuestCategory;
  duration: QuestDuration;
  note: string | null;
  link: string | null;
  travel_minutes: number | null;
  distance_km: number | null;
  active: boolean;
  done_on: string | null;
  done_before_app: boolean;
  memory: string | null;
  rating: number | null;
  created_at: string;
  done: boolean;
  xp: number; // paid when done, else what completing it pays
};

export type SideQuestBoard = {
  today: string;
  items: SideQuest[];
  durations: { key: QuestDuration; name: string; xp: number }[];
  categories: { key: QuestCategory; name: string; skill: string }[];
  week: { week_start: string; active: boolean; done: number; xp: number; titles: string[] };
  xp_total: number;
};

export type SideQuestInput = Partial<{
  title: string;
  category: QuestCategory;
  duration: QuestDuration;
  note: string | null;
  link: string | null;
  travel_minutes: number | null;
  distance_km: number | null;
  active: boolean;
  done_on: string | null;
  done_before_app: boolean;
  memory: string | null;
  rating: number | null;
}>;

export const sideQuestKeys = {
  board: ["sideQuests", "board", "v2"] as const,
};

export const useSideQuestBoard = () =>
  useQuery({ queryKey: sideQuestKeys.board, queryFn: () => api<SideQuestBoard>("/api/side-quests"), staleTime: 0 });

function useInvalidate() {
  const queryClient = useQueryClient();
  return () => {
    queryClient.invalidateQueries({ queryKey: ["sideQuests"] });
    queryClient.invalidateQueries({ queryKey: ["rpg"] });
  };
}

/** Create or edit a quest, start it, complete / un-complete it. Needs the server, so it fails at once offline. */
export function useSaveSideQuest() {
  const queryClient = useQueryClient();
  const invalidate = useInvalidate();
  return useMutation({
    retry: 0,
    mutationFn: ({ id, ...body }: SideQuestInput & { id?: number }) =>
      id ? api<SideQuest>(`/api/side-quests/${id}`, { method: "PATCH", body }) : api<SideQuest>("/api/side-quests", { method: "POST", body }),
    onSuccess: (quest) => {
      queryClient.setQueryData<SideQuestBoard>(sideQuestKeys.board, (board) =>
        board && { ...board, items: board.items.some((i) => i.id === quest.id) ? board.items.map((i) => (i.id === quest.id ? quest : i)) : [...board.items, quest] },
      );
      invalidate();
    },
  });
}

export function useDeleteSideQuest() {
  const queryClient = useQueryClient();
  const invalidate = useInvalidate();
  return useMutation({
    retry: 0,
    mutationFn: (id: number) => api(`/api/side-quests/${id}`, { method: "DELETE" }),
    onSuccess: (_data, id) => {
      queryClient.setQueryData<SideQuestBoard>(sideQuestKeys.board, (board) => board && { ...board, items: board.items.filter((i) => i.id !== id) });
      invalidate();
    },
  });
}
