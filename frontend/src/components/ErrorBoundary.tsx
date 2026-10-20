import { AlertTriangle, RotateCcw } from "lucide-react";
import { Component, type ErrorInfo, type ReactNode } from "react";

// Same key as the persister in main.tsx
const CACHE_KEY = "fitness-hub-cache";

// After a deploy the old lazy page chunks are gone; a reload fetches the new ones
const isChunkError = (error: Error) =>
  /dynamically imported module|Importing a module script failed|Failed to fetch|Loading chunk/i.test(error.message);

/** `resetKey`: a change clears the error (e.g. the route path, so navigating away recovers). */
type Props = { children: ReactNode; fullScreen?: boolean; resetKey?: string };
type State = { error: Error | null };

/** Catches render errors so a crash shows a message with a way out instead of a blank screen. */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidUpdate(prev: Props) {
    if (this.state.error && prev.resetKey !== this.props.resetKey) this.setState({ error: null });
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("UI crash", error, info.componentStack);
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;
    return <ErrorFallback error={error} fullScreen={this.props.fullScreen} onRetry={() => this.setState({ error: null })} />;
  }
}

function ErrorFallback({ error, fullScreen, onRetry }: { error: Error; fullScreen?: boolean; onRetry: () => void }) {
  const chunk = isChunkError(error);
  const clearCache = () => {
    if (!window.confirm("Smazat uložená data v telefonu? Neodeslané změny (např. offline série) se ztratí.")) return;
    try {
      localStorage.removeItem(CACHE_KEY);
    } catch {
      // Storage unavailable: the reload alone still helps
    }
    window.location.reload();
  };

  return (
    <div className={`flex flex-col items-center gap-4 px-4 text-center ${fullScreen ? "pt-safe min-h-dvh justify-center" : "py-16"}`}>
      <AlertTriangle size={40} className="text-amber-400" />
      <div>
        <h1 className="text-lg font-semibold text-zinc-50">{chunk ? "Je k dispozici nová verze" : "Něco se pokazilo"}</h1>
        <p className="mt-1 text-sm text-zinc-400">
          {chunk ? "Aplikace se aktualizovala, načti ji znovu." : "Tahle obrazovka spadla. Zkus to znovu, nebo aplikaci načti znovu."}
        </p>
      </div>
      <div className="flex flex-wrap justify-center gap-2">
        {!chunk && (
          <button onClick={onRetry} className="rounded-lg bg-zinc-800 px-4 py-2 text-sm text-zinc-100">
            Zkusit znovu
          </button>
        )}
        <button
          onClick={() => window.location.reload()}
          className="flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white"
        >
          <RotateCcw size={16} /> Načíst znovu
        </button>
      </div>
      {!chunk && (
        <>
          <details className="w-full max-w-md text-left text-xs text-zinc-500">
            <summary className="cursor-pointer text-center">Podrobnosti chyby</summary>
            <pre className="mt-2 overflow-auto whitespace-pre-wrap rounded-lg bg-zinc-900 p-3">
              {/* V8 stacks already start with "Name: message"; Safari's don't */}
              {error.stack?.startsWith(error.name) ? error.stack : `${error.name}: ${error.message}\n\n${error.stack ?? ""}`}
            </pre>
          </details>
          <button onClick={clearCache} className="text-xs text-zinc-500 underline">
            Pořád to padá? Smazat uložená data
          </button>
        </>
      )}
    </div>
  );
}
