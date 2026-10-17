import { Route, Routes } from "react-router";
import { Layout } from "./components/Layout";
import { Dashboard } from "./pages/Dashboard";
import { Placeholder } from "./pages/Placeholder";

export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="gym" element={<Placeholder title="Gym" />} />
        <Route path="run" element={<Placeholder title="Běh" />} />
        <Route path="coach" element={<Placeholder title="Kouč" />} />
        <Route path="settings" element={<Placeholder title="Nastavení" />} />
      </Route>
    </Routes>
  );
}
