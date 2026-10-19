import { lazy, Suspense } from "react";
import { Route, Routes } from "react-router";
import { Layout } from "./components/Layout";

// Each page is its own chunk: charts (recharts) only load with the dashboard
const Dashboard = lazy(() => import("./pages/Dashboard").then((m) => ({ default: m.Dashboard })));
const GymLogger = lazy(() => import("./pages/GymLogger").then((m) => ({ default: m.GymLogger })));
const ExerciseLibrary = lazy(() => import("./pages/ExerciseLibrary").then((m) => ({ default: m.ExerciseLibrary })));
const RunningPlan = lazy(() => import("./pages/RunningPlan").then((m) => ({ default: m.RunningPlan })));
const RunDetail = lazy(() => import("./pages/RunDetail").then((m) => ({ default: m.RunDetail })));
const AiCoach = lazy(() => import("./pages/AiCoach").then((m) => ({ default: m.AiCoach })));
const Nutrition = lazy(() => import("./pages/Nutrition").then((m) => ({ default: m.Nutrition })));
const FoodDatabase = lazy(() => import("./pages/FoodDatabase").then((m) => ({ default: m.FoodDatabase })));
const Habits = lazy(() => import("./pages/Habits").then((m) => ({ default: m.Habits })));
const Hero = lazy(() => import("./pages/Hero").then((m) => ({ default: m.Hero })));
const Settings = lazy(() => import("./pages/Settings").then((m) => ({ default: m.Settings })));

export function App() {
  return (
    <Suspense fallback={<div className="p-6 text-zinc-500">Načítám…</div>}>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="gym" element={<GymLogger />} />
          <Route path="gym/exercises" element={<ExerciseLibrary />} />
          <Route path="run" element={<RunningPlan />} />
          <Route path="run/:id" element={<RunDetail />} />
          <Route path="nutrition" element={<Nutrition />} />
          <Route path="nutrition/foods" element={<FoodDatabase />} />
          <Route path="habits" element={<Habits />} />
          <Route path="hero" element={<Hero />} />
          <Route path="coach" element={<AiCoach />} />
          <Route path="settings" element={<Settings />} />
        </Route>
      </Routes>
    </Suspense>
  );
}
