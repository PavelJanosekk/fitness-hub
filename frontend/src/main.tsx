import { createSyncStoragePersister } from "@tanstack/query-sync-storage-persister";
import { QueryClient } from "@tanstack/react-query";
import { PersistQueryClientProvider } from "@tanstack/react-query-persist-client";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";
import { App } from "./App";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { isGymWrite, registerGymMutations, resumePendingMutations } from "./api/gym";
import { isHabitWrite, registerHabitMutations } from "./api/habits";
import "./index.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, gcTime: 24 * 60 * 60 * 1000, retry: 1 },
    // Writes made offline wait and resume when the connection is back (docs/SPEC.md §3, A5)
    mutations: { networkMode: "offlineFirst", retry: 3 },
  },
});

// Registered before the cache is restored, so persisted gym and habit writes can resume after a reload
registerGymMutations(queryClient);
registerHabitMutations(queryClient);

// The cache (incl. paused mutations) survives reloads and app restarts: nothing typed in the gym is lost
const persister = createSyncStoragePersister({ storage: window.localStorage, key: "fitness-hub-cache" });
const persistOptions = {
  persister,
  maxAge: 7 * 24 * 60 * 60 * 1000,
  // Paused writes (the default) plus a gym or habit write still in flight or retrying when the app closes
  dehydrateOptions: {
    shouldDehydrateMutation: (m: Parameters<typeof isGymWrite>[0]) =>
      m.state.isPaused || (m.state.status === "pending" && (isGymWrite(m) || isHabitWrite(m))),
  },
};

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {/* Last resort when something outside a page (layout, watchers, providers) crashes */}
    <ErrorBoundary fullScreen>
      <PersistQueryClientProvider
        client={queryClient}
        persistOptions={persistOptions}
        onSuccess={() => resumePendingMutations(queryClient)}
      >
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </PersistQueryClientProvider>
    </ErrorBoundary>
  </StrictMode>,
);
