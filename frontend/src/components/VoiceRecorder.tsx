import { Mic, Square } from "lucide-react";
import { useEffect, useRef, useState } from "react";

/** Recording format the browser supports: Android Chrome → webm/opus, iOS Safari → mp4/aac. */
function pickMimeType(): string | undefined {
  const candidates = ["audio/webm;codecs=opus", "audio/mp4", "audio/ogg;codecs=opus", "audio/webm"];
  return candidates.find((type) => typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported(type));
}

/** Tap to record, tap again to send. Needs HTTPS (secure context) on phones. */
export function VoiceRecorder({
  onRecorded,
  disabled = false,
  className = "",
}: {
  onRecorded: (audio: Blob) => void;
  disabled?: boolean;
  className?: string;
}) {
  const [recording, setRecording] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);

  useEffect(() => {
    if (!recording) return;
    setSeconds(0);
    const timer = window.setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => window.clearInterval(timer);
  }, [recording]);

  const start = async () => {
    setError(null);
    if (!navigator.mediaDevices?.getUserMedia) {
      setError("Mikrofon funguje jen přes HTTPS");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = pickMimeType();
      const rec = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      chunks.current = [];
      rec.ondataavailable = (e) => e.data.size && chunks.current.push(e.data);
      rec.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunks.current, { type: rec.mimeType || mimeType || "audio/webm" });
        if (blob.size) onRecorded(blob);
      };
      rec.start();
      recorder.current = rec;
      setRecording(true);
    } catch {
      setError("Přístup k mikrofonu byl odmítnut");
    }
  };

  const stop = () => {
    recorder.current?.stop();
    recorder.current = null;
    setRecording(false);
  };

  return (
    <div className="relative">
      <button
        type="button"
        aria-label={recording ? "Odeslat nahrávku" : "Nahrát hlasem"}
        disabled={disabled}
        onClick={recording ? stop : start}
        className={`flex size-12 shrink-0 items-center justify-center rounded-full disabled:opacity-40 ${
          recording ? "animate-pulse bg-red-500 text-white" : "bg-zinc-800 text-zinc-100 active:bg-zinc-700"
        } ${className}`}
      >
        {recording ? <Square size={18} fill="currentColor" /> : <Mic size={22} />}
      </button>
      {recording && (
        <span className="absolute -top-7 left-1/2 -translate-x-1/2 rounded bg-red-500 px-1.5 text-xs tabular-nums text-white">
          {Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, "0")}
        </span>
      )}
      {error && <span className="absolute -top-7 right-0 whitespace-nowrap rounded bg-zinc-800 px-2 text-xs text-amber-300">{error}</span>}
    </div>
  );
}
