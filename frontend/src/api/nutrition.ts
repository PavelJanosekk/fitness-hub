import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type { Tier } from "./coach";
import type { Meal, MealItem } from "./types";

export type FoodSource = "usda" | "openfoodfacts" | "kaloricke_tabulky" | "custom" | "web_estimate" | "recipe";
export type MealType = "breakfast" | "morning_snack" | "lunch" | "afternoon_snack" | "dinner" | "second_dinner" | "other";

export const MEAL_TYPES: readonly (readonly [MealType, string])[] = [
  ["breakfast", "Snídaně"],
  ["morning_snack", "Dopolední svačina"],
  ["lunch", "Oběd"],
  ["afternoon_snack", "Odpolední svačina"],
  ["dinner", "Večeře"],
  ["second_dinner", "Druhá večeře"],
  ["other", "Ostatní"],
];
export const mealTypeLabel = (type: string) => MEAL_TYPES.find(([key]) => key === type)?.[1] ?? type;

/** The meal slot for a manual entry right now. */
export function mealTypeNow(date = new Date()): MealType {
  const hour = date.getHours();
  if (hour < 10) return "breakfast";
  if (hour < 12) return "morning_snack";
  if (hour < 15) return "lunch";
  if (hour < 18) return "afternoon_snack";
  if (hour < 21) return "dinner";
  return "second_dinner";
}

export const SOURCE_LABELS: Record<string, string> = {
  usda: "USDA",
  openfoodfacts: "OFF",
  kaloricke_tabulky: "KT",
  custom: "Vlastní",
  web_estimate: "Odhad AI",
  recipe: "Recept",
};

export type Macros = {
  kcal: number | null;
  protein_g: number | null;
  carbs_g: number | null;
  fat_g: number | null;
  sugar_g?: number | null;
  saturated_fat_g?: number | null;
  fiber_g?: number | null;
  salt_g?: number | null;
};
export type Candidate = {
  ref: string; // "food:<id>" | "off:<ean>" | "web"
  name: string;
  source: FoodSource;
  brand: string | null;
  per_100g: Macros;
  micronutrients: Record<string, number>;
  grounded?: boolean; // web estimates: found on the web, or the model's own estimate
};
export type MealItemInput = {
  user_phrase: string;
  canonical_name_cs: string;
  amount_g: number;
  usda_query_en?: string | null;
  is_branded?: boolean;
  brand_search_query?: string | null;
  food_id?: number | null;
};
export type DraftItem = {
  input: MealItemInput;
  amount_g: number;
  confirmed: boolean;
  confidence: number | null;
  chosen: Candidate | null;
  candidates: Candidate[];
};
export type MealDraft = { kind: "meal"; date: string; meal_type: MealType; raw_input?: string; items: DraftItem[] };
export type SavedMeal = { meal_id: string; date: string; meal_type: MealType; items: { food: string; grams: number; kcal: number }[] };
export type NutritionChatResponse = {
  reply: string;
  conversation_id: string;
  tool_calls_made: string[];
  drafts: MealDraft[];
  saved_meals: SavedMeal[];
  model: string | null;
};

export type NutrientTotal = {
  key: string;
  label: string;
  unit: string;
  amount: number | null;
  coverage: number | null; // 0-1 share of the day's kcal behind `amount`
  target: number | null;
  percent: number | null;
};
export type DaySummary = { date: string; training_day: boolean; meals: Meal[]; nutrients: NutrientTotal[] };

export type Portion = { label: string; grams: number };
export type Food = Required<Macros> & {
  id: number;
  name: string;
  name_cs: string | null;
  name_en: string | null;
  brand: string | null;
  category: string | null;
  ean: string | null;
  source: FoodSource;
  is_raw: boolean | null;
  kcal: number;
  protein_g: number;
  carbs_g: number;
  fat_g: number;
  micronutrients: Record<string, number>;
  portions: Portion[];
  use_count: number;
};
export type FoodInput = Partial<Omit<Food, "id" | "name" | "source" | "use_count" | "category" | "is_raw">>;

export type Profile = {
  sex: "male" | "female" | null;
  birth_year: number | null;
  height_cm: number | null;
  kcal_target: number | null;
  kcal_target_training_day: number | null;
  protein_target_g: number | null;
  carbs_target_g: number | null;
  fat_target_g: number | null;
  fiber_target_g: number | null;
};

export const nutritionKeys = {
  summary: (date: string) => ["nutrition", "summary", date] as const,
  foods: (q: string, source: string) => ["nutrition", "foods", q, source] as const,
  food: (id: number) => ["nutrition", "food", id] as const,
  profile: ["nutrition", "profile"] as const,
};

export const useDaySummary = (date: string) =>
  useQuery({ queryKey: nutritionKeys.summary(date), queryFn: () => api<DaySummary>(`/api/nutrition/summary?date=${date}`) });

export function useFoods(q: string, source = "") {
  const params = new URLSearchParams({ limit: "40" });
  if (q.trim()) params.set("q", q.trim());
  if (source) params.set("source", source);
  return useQuery({
    queryKey: nutritionKeys.foods(q.trim(), source),
    queryFn: () => api<Food[]>(`/api/nutrition/foods?${params}`),
    staleTime: 60_000,
  });
}

export const useFood = (id: number | null) =>
  useQuery({ queryKey: nutritionKeys.food(id ?? 0), queryFn: () => api<Food>(`/api/nutrition/foods/${id}`), enabled: id !== null });

export const useProfile = () => useQuery({ queryKey: nutritionKeys.profile, queryFn: () => api<Profile>("/api/nutrition/profile") });

function useInvalidateIntake() {
  const queryClient = useQueryClient();
  return () => {
    queryClient.invalidateQueries({ queryKey: ["nutrition"] });
    queryClient.invalidateQueries({ queryKey: ["metrics"] });
  };
}

export function useSaveProfile() {
  const invalidate = useInvalidateIntake();
  return useMutation({
    mutationFn: (profile: Profile) => api<Profile>("/api/nutrition/profile", { method: "PUT", body: profile }),
    onSettled: invalidate,
  });
}

/** Add a food with grams, or change an item's grams; the client id makes a retry harmless. */
export function usePutItem() {
  const invalidate = useInvalidateIntake();
  return useMutation({
    mutationKey: ["nutrition", "item"],
    mutationFn: ({ id, ...body }: { id: string; food_id: number; amount_g: number; meal_type: MealType; date: string }) =>
      api<MealItem>(`/api/nutrition/items/${id}`, { method: "PUT", body }),
    onSettled: invalidate,
  });
}

export function useDeleteItem() {
  const invalidate = useInvalidateIntake();
  return useMutation({
    mutationKey: ["nutrition", "delete-item"],
    mutationFn: (id: string) => api(`/api/nutrition/items/${id}`, { method: "DELETE" }),
    onSettled: invalidate,
  });
}

export function useConfirmDraft() {
  const invalidate = useInvalidateIntake();
  return useMutation({
    mutationFn: (body: {
      id: string;
      date: string;
      meal_type: MealType;
      raw_input?: string;
      items: { input: MealItemInput; candidate: Candidate; amount_g: number }[];
    }) => api<Meal>("/api/nutrition/drafts/confirm", { method: "POST", body }),
    onSettled: invalidate,
  });
}

export function useSaveFood() {
  const invalidate = useInvalidateIntake();
  return useMutation({
    mutationFn: ({ id, ...body }: FoodInput & { id?: number }) =>
      id ? api<Food>(`/api/nutrition/foods/${id}`, { method: "PATCH", body }) : api<Food>("/api/nutrition/foods", { method: "POST", body }),
    onSettled: invalidate,
  });
}

export function useDeleteFood() {
  const invalidate = useInvalidateIntake();
  return useMutation({ mutationFn: (id: number) => api(`/api/nutrition/foods/${id}`, { method: "DELETE" }), onSettled: invalidate });
}

export const sendNutritionChat = (message: string, conversation_id: string | null, model: Tier = "fast") =>
  api<NutritionChatResponse>("/api/nutrition/chat", { method: "POST", body: { message, model, conversation_id } });

export function sendNutritionVoice(audio: Blob, conversationId: string | null) {
  const form = new FormData();
  const extension = audio.type.includes("mp4") ? "m4a" : audio.type.includes("ogg") ? "ogg" : "webm";
  form.append("audio", audio, `recording.${extension}`);
  if (conversationId) form.append("conversation_id", conversationId);
  return api<NutritionChatResponse>("/api/nutrition/voice", { method: "POST", form });
}

/** kcal of `grams` of a candidate or food (per-100 g values). */
export const kcalFor = (per100g: { kcal: number | null }, grams: number) => (per100g.kcal === null ? null : (per100g.kcal * grams) / 100);
