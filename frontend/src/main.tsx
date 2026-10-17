import { createSyncStoragePersister } from "@tanstack/query-sync-storage-persister";
import { QueryClient } from "@tanstack/react-query";
import { PersistQueryClientProvider } from "@tanstack/react-query-persist-client";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";
import { App } from "./App";
import { registerGymMutations } from "./api/gym";
import "./index.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, gcTime: 24 * 60 * 60 * 1000, retry: 1 },
    // Writes made offline wait and resume when the connection is back (docs/SPEC.md §3, A5)
    mutations: { networkMode: "offlineFirst", retry: 3 },
  },
});

// Registered before the cache is restored, so persisted gym writes can resume after a reload
registerGymMutations(queryClient);

// The cache (incl. paused mutations) survives reloads and app restarts: nothing typed in the gym is lost
const persister = createSyncStoragePersister({ storage: window.localStorage, key: "fitness-hub-cache" });

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <PersistQueryClientProvider
      client={queryClient}
      persistOptions={{ persister, maxAge: 7 * 24 * 60 * 60 * 1000 }}
      onSuccess={() => queryClient.resumePausedMutations()}
    >
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </PersistQueryClientProvider>
  </StrictMode>,
);
