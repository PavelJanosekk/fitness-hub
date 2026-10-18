import { useQueryClient } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Database, Plus, SendHorizontal, Target, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import {
  type MealDraft,
  type MealType,
  type NutritionChatResponse,
  mealTypeLabel,
  sendNutritionChat,
  sendNutritionVoice,
  useDaySummary,
  useDeleteItem,
  usePutItem,
} from "../api/nutrition";
import type { Meal, MealItem } from "../api/types";
import { Card, PageHeader } from "../components/Layout";
import { Markdown } from "../components/Markdown";
import { AddFoodSheet } from "../components/nutrition/AddFoodSheet";
import { EnergySummary } from "../components/nutrition/EnergySummary";
import { MealDraftCard } from "../components/nutrition/MealDraftCard";
import { MacroSummary, MicroGrid } from "../components/nutrition/NutrientBars";
import { TargetsSheet } from "../components/nutrition/TargetsSheet";
import { DecimalInput, parseDecimal } from "../components/ui";
import { VoiceRecorder } from "../components/VoiceRecorder";
import { addDays, formatDay, formatNumber, isoDate } from "../lib/format";
import { errorText } from "./AiCoach";

const CONVERSATION_KEY = "fitness-hub-nutrition-conversation";
const PROMPTS = ["Co jsem dnes jedl a kolik mi chybí bílkovin?", "Jak jsem na tom dnes s vitamíny a minerály?"];

type Message = { role: "user" | "model"; content: string; drafts?: MealDraft[] };

export function Nutrition() {
  const today = isoDate();
  const [date, setDate] = useState(today);
  const summary = useDaySummary(date);
  const [adding, setAdding] = useState<{ mealType?: MealType } | null>(null);
  const [targets, setTargets] = useState(false);

  return (
    <>
      <PageHeader
        title="Jídlo"
        action={
          <div className="flex items-center gap-1">
            <button onClick={() => setTargets(true)} aria-label="Cíle" className="rounded-full p-2 text-zinc-400 active:bg-zinc-800">
              <Target size={20} />
            </button>
            <Link to="/nutrition/foods" aria-label="Databáze potravin" className="rounded-full p-2 text-zinc-400 active:bg-zinc-800">
              <Database size={20} />
            </Link>
          </div>
        }
      />
      <div className="mb-3 flex items-center justify-between">
        <button onClick={() => setDate(addDays(date, -1))} aria-label="Předchozí den" className="rounded-full p-2 text-zinc-400 active:bg-zinc-800">
          <ChevronLeft size={20} />
        </button>
        <button onClick={() => setDate(today)} className="font-medium">
          {date === today ? "Dnes" : formatDay(date)}
        </button>
        <button
          onClick={() => setDate(addDays(date, 1))}
          disabled={date >= today}
          aria-label="Další den"
          className="rounded-full p-2 text-zinc-400 active:bg-zinc-800 disabled:opacity-30"
        >
          <ChevronRight size={20} />
        </button>
      </div>

      <div className="space-y-3">
        <Card>
          {summary.data ? <MacroSummary nutrients={summary.data.nutrients} trainingDay={summary.data.training_day} /> : <p className="text-zinc-500">Načítám…</p>}
          <EnergySummary date={date} onOpenTargets={() => setTargets(true)} />
        </Card>
        <Assistant date={date} />
        <Meals meals={summary.data?.meals ?? []} date={date} onAdd={(mealType) => setAdding({ mealType })} />
        {summary.data && (
          <Card>
            <MicroGrid nutrients={summary.data.nutrients} />
          </Card>
        )}
      </div>

      {adding && <AddFoodSheet date={date} mealType={adding.mealType} onClose={() => setAdding(null)} />}
      {targets && <TargetsSheet onClose={() => setTargets(false)} />}
    </>
  );
}

/** Dictate or type what you ate; known foods save directly, the rest come back as cards to confirm. */
function Assistant({ date }: { date: string }) {
  const queryClient = useQueryClient();
  const [conversationId, setConversationId] = useState<string | null>(() => localStorage.getItem(CONVERSATION_KEY));
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (messages.length) bottom.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [messages, busy]);

  const handle = async (shown: string, request: () => Promise<NutritionChatResponse>) => {
    setMessages((m) => [...m, { role: "user", content: shown }]);
    setBusy(true);
    try {
      const response = await request();
      localStorage.setItem(CONVERSATION_KEY, response.conversation_id);
      setConversationId(response.conversation_id);
      setMessages((m) => [...m, { role: "model", content: response.reply, drafts: response.drafts }]);
      if (response.saved_meals.length) {
        queryClient.invalidateQueries({ queryKey: ["nutrition"] });
        queryClient.invalidateQueries({ queryKey: ["metrics"] });
      }
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
    void handle(message, () => sendNutritionChat(message, conversationId, date));
  };

  return (
    <Card>
      {messages.length === 0 && (
        <div className="mb-3 space-y-2">
          <p className="text-sm text-zinc-400">Napiš nebo nadiktuj, co jsi snědl, třeba „k obědu 200 g kuřecích stehen a 300 g brambor“.</p>
          <div className="flex flex-wrap gap-2">
            {PROMPTS.map((p) => (
              <button key={p} onClick={() => send(p)} className="rounded-lg bg-zinc-800 px-2.5 py-1.5 text-left text-xs text-zinc-300 active:bg-zinc-700">
                {p}
              </button>
            ))}
          </div>
        </div>
      )}
      {messages.length > 0 && (
        <div className="mb-3 max-h-[60dvh] space-y-3 overflow-y-auto">
          {messages.map((m, i) => (
            <div key={i} className={m.role === "user" ? "flex justify-end" : ""}>
              <div className={m.role === "user" ? "max-w-[85%] rounded-2xl rounded-br-md bg-emerald-600/90 px-3.5 py-2 text-on-accent" : "w-full text-sm"}>
                {m.role === "user" ? m.content : <Markdown text={m.content} />}
                {m.drafts?.map((d, j) => <MealDraftCard key={j} draft={d} />)}
              </div>
            </div>
          ))}
          {busy && <p className="animate-pulse text-sm text-zinc-500">Zpracovávám…</p>}
          <div ref={bottom} />
        </div>
      )}
      <form onSubmit={(e) => (e.preventDefault(), send(input))} className="flex items-end gap-2">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && (e.preventDefault(), send(input))}
          rows={1}
          placeholder="Co jsi snědl?"
          className="max-h-32 min-h-12 flex-1 resize-none rounded-2xl border border-zinc-700 bg-zinc-950 px-3.5 py-3 outline-none focus:border-emerald-500"
        />
        {input.trim() ? (
          <button type="submit" disabled={busy} aria-label="Odeslat" className="flex size-12 shrink-0 items-center justify-center rounded-full bg-emerald-500 text-on-accent disabled:opacity-40">
            <SendHorizontal size={20} />
          </button>
        ) : (
          <VoiceRecorder onRecorded={(audio) => void handle("🎤 hlasová zpráva", () => sendNutritionVoice(audio, conversationId, date))} disabled={busy} />
        )}
      </form>
    </Card>
  );
}

function Meals({ meals, date, onAdd }: { meals: Meal[]; date: string; onAdd: (mealType?: MealType) => void }) {
  return (
    <Card>
      <div className="mb-2 flex items-center justify-between">
        <h2 className="font-semibold">Jídla</h2>
        <button onClick={() => onAdd()} className="flex items-center gap-1 rounded-lg px-2 py-1 text-sm text-emerald-400 active:bg-zinc-800">
          <Plus size={16} /> Přidat
        </button>
      </div>
      {meals.length === 0 && <p className="text-sm text-zinc-500">Zatím nic.</p>}
      <div className="divide-y divide-zinc-800">
        {meals.map((meal) => (
          <div key={meal.id} className="py-3 first:pt-0 last:pb-0">
            <div className="mb-1 flex items-center justify-between">
              <span className="text-base font-semibold text-zinc-100">{mealTypeLabel(meal.meal_type)}</span>
              <span className="flex items-center gap-1.5 text-base font-semibold tabular-nums text-zinc-100">
                {formatNumber(meal.items.reduce((sum, i) => sum + i.kcal, 0))} kcal
                <button onClick={() => onAdd(meal.meal_type as MealType)} aria-label="Přidat do jídla" className="rounded p-1 text-zinc-400 active:bg-zinc-800">
                  <Plus size={16} />
                </button>
              </span>
            </div>
            <ul>
              {meal.items.map((item) => (
                <ItemRow key={item.id} item={item} mealType={meal.meal_type as MealType} date={date} />
              ))}
            </ul>
          </div>
        ))}
      </div>
    </Card>
  );
}

/** One eaten item; grams of a food item are editable in place, any item can be removed. */
function ItemRow({ item, mealType, date }: { item: MealItem; mealType: MealType; date: string }) {
  const putItem = usePutItem();
  const deleteItem = useDeleteItem();
  const [editing, setEditing] = useState<string | null>(null);

  const commit = () => {
    const grams = parseDecimal(editing ?? "");
    setEditing(null);
    if (item.food_id && grams && grams > 0 && grams !== item.amount_g) {
      putItem.mutate({ id: item.id, food_id: item.food_id, amount_g: grams, meal_type: mealType, date });
    }
  };

  return (
    <li className="flex items-center gap-2 py-1.5 text-sm">
      <div className="min-w-0 flex-1">
        <p className="line-clamp-2 leading-snug text-zinc-300">{item.food_name ?? item.label}</p>
        {item.food_name && item.label !== item.food_name && <p className="truncate text-xs text-zinc-500">{item.label}</p>}
      </div>
      {item.food_id ? (
        editing !== null ? (
          <form onSubmit={(e) => (e.preventDefault(), commit())} className="w-20">
            <DecimalInput ariaLabel="Gramy" value={editing} onChange={setEditing} autoFocus className="!min-h-9 text-right !text-base" />
          </form>
        ) : (
          <button onClick={() => setEditing(String(item.amount_g ?? "").replace(".", ","))} className="rounded px-1.5 py-1 tabular-nums text-zinc-400 active:bg-zinc-800">
            {formatNumber(item.amount_g)} g
          </button>
        )
      ) : null}
      {editing !== null ? (
        <button onClick={commit} className="rounded-lg bg-emerald-500 px-2 py-1 text-sm text-on-accent">
          OK
        </button>
      ) : (
        <>
          <span className="w-16 text-right tabular-nums text-zinc-500">{formatNumber(item.kcal)} kcal</span>
          <button onClick={() => deleteItem.mutate(item.id)} aria-label="Smazat" className="rounded p-1.5 text-zinc-600 active:bg-zinc-800">
            <Trash2 size={15} />
          </button>
        </>
      )}
    </li>
  );
}
