import { Route, Routes } from "react-router";
import { Layout } from "./components/Layout";
import { Dashboard } from "./pages/Dashboard";
import { GymLogger } from "./pages/GymLogger";
import { Placeholder } from "./pages/Placeholder";
import { RunningPlan } from "./pages/RunningPlan";

export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="gym" element={<GymLogger />} />
        <Route path="run" element={<RunningPlan />} />
        <Route path="coach" element={<Placeholder title="Kouč" />} />
        <Route path="settings" element={<Placeholder title="Nastavení" />} />
      </Route>
    </Routes>
  );
}
