import { useQueryClient } from "@tanstack/react-query";
import { Plus, SendHorizontal } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { ApiError } from "../api/client";
import { type ChatResponse, type Draft, getConversation, sendChat, sendVoice, type Tier } from "../api/coach";
import { pullServerSets } from "../api/gym";
import { DraftCard } from "../components/DraftCard";
import { PageHeader } from "../components/Layout";
import { Markdown } from "../components/Markdown";
import { Segmented } from "../components/ui";
import { VoiceRecorder } from "../components/VoiceRecorder";

type Message = { role: "user" | "model"; content: string; drafts?: Draft[]; tools?: string[] };

const CONVERSATION_KEY = "fitness-hub-coach-conversation";
const TIERS = [
  ["fast", "Rychlý"],
  ["smart", "Hloubkový"],
] as const;
const PROMPTS = [
  "Analyzuj moji stagnaci a objem partií za poslední měsíc",
  "Zhodnoť můj běžecký plán na tento týden vůči únavě z fitka",
  "Jak se vyvíjí moje aerobní efektivita při stejném tepu?",
  "Co mám dnes a zítra podle plánu?",
];

export function errorText(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 429) return "Gemini je teď přetížený (limit free tier), zkus to za chvíli.";
    if (error.status === 503) return "AI není nastavená (chybí klíč nebo model).";
    return `Chyba ${error.status}: ${error.message}`;
  }
  return navigator.onLine ? "Nepodařilo se spojit se serverem." : "Jsi offline, kouč potřebuje připojení.";
}

export function AiCoach() {
  const queryClient = useQueryClient();
  const [conversationId, setConversationId] = useState<string | null>(() => localStorage.getItem(CONVERSATION_KEY));
  const [messages, setMessages] = useState<Message[]>([]);
  const [tier, setTier] = useState<Tier>("fast");
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!conversationId) return;
    getConversation(conversationId)
      .then((c) => setMessages(c.messages.map((m) => ({ role: m.role, content: m.content }))))
      .catch(() => {
        localStorage.removeItem(CONVERSATION_KEY);
        setConversationId(null);
      });
  }, [conversationId]);

  useEffect(() => bottom.current?.scrollIntoView({ behavior: "smooth" }), [messages, busy]);

  const handle = async (userText: string, request: () => Promise<ChatResponse>) => {
    setMessages((m) => [...m, { role: "user", content: userText }]);
    setBusy(true);
    try {
      const response = await request();
      localStorage.setItem(CONVERSATION_KEY, response.conversation_id);
      if (response.conversation_id !== conversationId) setConversationId(response.conversation_id);
      setMessages((m) => [...m, { role: "model", content: response.reply, drafts: response.drafts, tools: response.tool_calls_made }]);
      for (const saved of response.saved_sets) await pullServerSets(queryClient, saved.workout_id).catch(() => undefined);
      if (response.saved_sets.length) queryClient.invalidateQueries({ queryKey: ["workouts"] });
    } catch (error) {
      setMessages((m) => [...m, { role: "model", content: `⚠️ ${errorText(error)}` }]);
    } finally {
      setBusy(false);
    }
  };

  const send = (text: string) => {
    const message = text.trim();
    if (!message || busy) return;
    setInput("");
    void handle(message, () => sendChat(message, tier, conversationId));
  };

  const sendAudio = (audio: Blob) =>
    void handle("🎤 hlasová zpráva", () => sendVoice(audio, { conversationId, model: tier }));

  const reset = () => {
    localStorage.removeItem(CONVERSATION_KEY);
    setConversationId(null);
    setMessages([]);
  };

  return (
    <div className="flex min-h-[calc(100dvh-7rem)] flex-col md:min-h-[calc(100dvh-2rem)]">
      <PageHeader
        title="Kouč"
        action={
          <button onClick={reset} aria-label="Nová konverzace" className="flex items-center gap-1 rounded-full p-2 text-sm text-zinc-400 active:bg-zinc-800">
            <Plus size={18} /> Nová
          </button>
        }
      />
      <div className="mb-3">
        <Segmented options={TIERS} value={tier} onChange={setTier} />
      </div>

      <div className="flex-1 space-y-3">
        {messages.length === 0 && (
          <div className="space-y-2">
            <p className="text-sm text-zinc-400">Zeptej se, nebo nadiktuj odcvičené série.</p>
            {PROMPTS.map((p) => (
              <button key={p} onClick={() => send(p)} className="block w-full rounded-xl bg-zinc-900 p-3 text-left text-sm text-zinc-200 active:bg-zinc-800">
                {p}
              </button>
            ))}
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={m.role === "user" ? "flex justify-end" : ""}>
            <div className={m.role === "user" ? "max-w-[85%] rounded-2xl rounded-br-md bg-emerald-600/90 px-3.5 py-2 text-zinc-950" : "w-full"}>
              {m.role === "user" ? m.content : <Markdown text={m.content} />}
              {m.drafts?.map((d, j) => <DraftCard key={j} draft={d} onSaved={(id) => void pullServerSets(queryClient, id)} />)}
              {m.tools && m.tools.length > 0 && <p className="mt-1 text-xs text-zinc-600">nástroje: {m.tools.join(", ")}</p>}
            </div>
          </div>
        ))}
        {busy && <p className="animate-pulse text-sm text-zinc-500">Kouč přemýšlí…</p>}
        <div ref={bottom} />
      </div>

      <form
        onSubmit={(e) => (e.preventDefault(), send(input))}
        className="sticky bottom-[calc(env(safe-area-inset-bottom)+4.25rem)] mt-3 flex items-end gap-2 bg-zinc-950 py-2 md:bottom-0"
      >
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && (e.preventDefault(), send(input))}
          rows={1}
          placeholder="Napiš zprávu…"
          className="max-h-32 min-h-12 flex-1 resize-none rounded-2xl border border-zinc-700 bg-zinc-900 px-3.5 py-3 outline-none focus:border-emerald-500"
        />
        {input.trim() ? (
          <button type="submit" disabled={busy} aria-label="Odeslat" className="flex size-12 shrink-0 items-center justify-center rounded-full bg-emerald-500 text-zinc-950 disabled:opacity-40">
            <SendHorizontal size={20} />
          </button>
        ) : (
          <VoiceRecorder onRecorded={sendAudio} disabled={busy} />
        )}
      </form>
    </div>
  );
}
