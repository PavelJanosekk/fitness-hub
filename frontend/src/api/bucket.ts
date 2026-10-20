import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";

export type Category = "travel" | "expedition" | "experience" | "adrenaline" | "sport" | "skill" | "food" | "wellbeing";
export type Season = "summer" | "winter";
export type BucketAutoRule = "marathon" | "exercise" | "hike" | "continents";
export type BucketStep = { id: number; position: number; title: string; done_on: string | null };

export type BucketItem = {
  id: number;
  title: string;
  category: Category;
  rarity: 1 | 2 | 3 | 4;
  note: string | null;
  link: string | null;
  travel_time: string | null;
  season: Season | null;
  cost: number | null;
  planned_for: string | null;
  done_on: string | null; // set by hand
  done_before_app: boolean;
  memory: string | null;
  rating: number | null;
  year_goal: number | null;
  auto_rule: BucketAutoRule | null;
  auto_exercise_id: number | null;
  auto_exercise_name: string | null;
  auto_threshold: number | null;
  country_codes: string[];
  lat: number | null;
  lon: number | null;
  created_at: string;
  steps: BucketStep[];
  done: boolean;
  completed_on: string | null; // effective day (by hand or auto); null when open or done before the app
  source: "manual" | "auto" | "before" | null;
  auto_label: string | null;
  auto_progress: string | null;
  xp: number;
  goal_xp: number;
};

export type Country = { code: string; continent: string | null; visited_on: string | null; on_map: boolean; items: string[] };

export type BucketBoard = {
  today: string;
  items: BucketItem[];
  countries: Country[];
  continents: Record<string, string | null>;
  continent_names: Record<string, string>;
  country_continents: Record<string, string>;
  rarities: { level: number; name: string; xp: number }[];
  categories: Record<Category, string>;
  year_quest: { year: number; done: number; target: number; xp: number; reached_on: string | null };
  xp_total: number;
  step_xp: number;
  year_goal_share: number;
};

export type BucketInput = Partial<{
  title: string;
  category: Category;
  rarity: number;
  note: string | null;
  link: string | null;
  travel_time: string | null;
  season: Season | null;
  cost: number | null;
  planned_for: string | null;
  done_on: string | null;
  done_before_app: boolean;
  memory: string | null;
  rating: number | null;
  year_goal: number | null;
  auto_rule: BucketAutoRule | null;
  auto_exercise_id: number | null;
  auto_threshold: number | null;
  country_codes: string[];
  lat: number | null;
  lon: number | null;
  steps: string[];
}>;

export const bucketKeys = {
  board: ["bucket", "board", "v1"] as const,
};

// Auto rules read gym, runs and the map, so the board is refetched whenever it is shown
export const useBucketBoard = () =>
  useQuery({ queryKey: bucketKeys.board, queryFn: () => api<BucketBoard>("/api/bucket"), staleTime: 0 });

function useInvalidate() {
  const queryClient = useQueryClient();
  return () => {
    queryClient.invalidateQueries({ queryKey: ["bucket"] });
    queryClient.invalidateQueries({ queryKey: ["rpg"] });
  };
}

/** Patch the board right away with the server's answer (the item as it is now), then refetch around it. */
function useReplaceItem() {
  const queryClient = useQueryClient();
  return (item: BucketItem) =>
    queryClient.setQueryData<BucketBoard>(bucketKeys.board, (board) =>
      board && { ...board, items: board.items.some((i) => i.id === item.id) ? board.items.map((i) => (i.id === item.id ? item : i)) : [...board.items, item] },
    );
}

/** Create or edit an item, complete / un-complete it, plan it, star it. Needs the server, so it fails at once offline. */
export function useSaveBucketItem() {
  const invalidate = useInvalidate();
  const replace = useReplaceItem();
  return useMutation({
    retry: 0,
    mutationFn: ({ id, ...body }: BucketInput & { id?: number }) =>
      id ? api<BucketItem>(`/api/bucket/${id}`, { method: "PATCH", body }) : api<BucketItem>("/api/bucket", { method: "POST", body }),
    onSuccess: (item) => {
      replace(item);
      invalidate();
    },
  });
}

export function useDeleteBucketItem() {
  const queryClient = useQueryClient();
  const invalidate = useInvalidate();
  return useMutation({
    retry: 0,
    mutationFn: (id: number) => api(`/api/bucket/${id}`, { method: "DELETE" }),
    onSuccess: (_data, id) => {
      queryClient.setQueryData<BucketBoard>(bucketKeys.board, (board) => board && { ...board, items: board.items.filter((i) => i.id !== id) });
      invalidate();
    },
  });
}

/** Add a step to an item, rename / tick / untick one, or delete one; every call answers with the whole item. */
export function useSaveStep() {
  const invalidate = useInvalidate();
  const replace = useReplaceItem();
  return useMutation({
    retry: 0,
    mutationFn: (write: { itemId: number; title: string } | { stepId: number; title?: string; done_on?: string | null } | { stepId: number; remove: true }) => {
      if ("itemId" in write) return api<BucketItem>(`/api/bucket/${write.itemId}/steps`, { method: "POST", body: { title: write.title } });
      if ("remove" in write) return api<BucketItem>(`/api/bucket/steps/${write.stepId}`, { method: "DELETE" });
      const { stepId, ...body } = write;
      return api<BucketItem>(`/api/bucket/steps/${stepId}`, { method: "PATCH", body });
    },
    onSuccess: (item) => {
      replace(item);
      invalidate();
    },
  });
}

/** Mark / unmark a country on the world map (`visited_on` null = before the app, left out = today). */
export function useSetCountry() {
  const invalidate = useInvalidate();
  return useMutation({
    retry: 0,
    mutationFn: ({ code, ...body }: { code: string; visited: boolean; visited_on?: string | null }) =>
      api<Country[]>(`/api/bucket/countries/${code}`, { method: "PUT", body }),
    onSuccess: invalidate,
  });
}
