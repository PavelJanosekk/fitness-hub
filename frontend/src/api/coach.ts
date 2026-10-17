import { api } from "./client";

export type Tier = "fast" | "smart";
export type Draft = {
  kind: "workout_sets";
  reason: "exercise_uncertain" | "exercise_unknown" | "implausible_numbers";
  input_exercise_name: string;
  candidates: { exercise_id: number; name: string; similarity: number }[];
  workout_id: string | null;
  sets: { weight_kg?: number; reps?: number; rpe?: number; set_type?: string }[];
  last_session_weights: number[];
};
export type SavedSets = { workout_id: string; exercise: string; sets_saved: number };
export type ChatResponse = {
  reply: string;
  conversation_id: string;
  tool_calls_made: string[];
  drafts: Draft[];
  saved_sets: SavedSets[];
  model: string | null;
};
export type ChatMessage = { role: "user" | "model"; content: string; created_at: string };

export const sendChat = (message: string, model: Tier, conversation_id: string | null) =>
  api<ChatResponse>("/api/ai/chat", { method: "POST", body: { message, model, conversation_id } });

export function sendVoice(audio: Blob, opts: { text?: string; workoutId?: string; conversationId?: string | null; model: Tier }) {
  const form = new FormData();
  const extension = audio.type.includes("mp4") ? "m4a" : audio.type.includes("ogg") ? "ogg" : "webm";
  form.append("audio", audio, `recording.${extension}`);
  if (opts.text) form.append("text", opts.text);
  if (opts.workoutId) form.append("workout_id", opts.workoutId);
  if (opts.conversationId) form.append("conversation_id", opts.conversationId);
  form.append("model", opts.model);
  return api<ChatResponse>("/api/ai/voice-workout", { method: "POST", form });
}

export const getConversation = (id: string) =>
  api<{ id: string; messages: ChatMessage[] }>(`/api/ai/conversations/${id}`);

export const confirmDraft = (body: { exercise_id: number; sets: Draft["sets"]; workout_id: string | null }) =>
  api<SavedSets>("/api/ai/drafts/confirm", { method: "POST", body });
