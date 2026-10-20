import { Settings } from "lucide-react";
import { Suspense } from "react";
import { Link, NavLink, Navigate, Outlet, useLocation } from "react-router";
import { useCharacter } from "../api/rpg";
import { PageHeader } from "../components/Layout";

const TABS = [
  { to: "/hero", label: "Rutina", end: true },
  { to: "/hero/bucket", label: "Bucket list", end: false },
  { to: "/hero/character", label: "Postava", end: true },
] as const;

/** The Hrdina tab (E36): Rutina, Bucket list and Postava (character, XP history) as sub-tabs; side quests come later. */
export function HeroLayout() {
  const { data: c } = useCharacter();
  return (
    <>
      <PageHeader
        title="Hrdina"
        action={
          <div className="flex items-center gap-1">
            {c && (
              <Link to="/hero/character" className="rounded-full border border-emerald-700 px-2.5 py-1 text-xs font-semibold text-emerald-300">
                Lv {c.level} · {c.title}
              </Link>
            )}
            <Link to="/settings" aria-label="Nastavení" className="rounded-full p-2 text-zinc-400 active:bg-zinc-800 md:hidden">
              <Settings size={22} />
            </Link>
          </div>
        }
      />
      <nav aria-label="Hrdina" className="ui-seg mb-3 grid grid-cols-3 rounded-xl p-1 text-sm">
        {TABS.map((tab) => (
          <NavLink key={tab.to} to={tab.to} end={tab.end} className="ui-seg-item flex min-h-9 items-center justify-center rounded-lg px-2">
            {tab.label}
          </NavLink>
        ))}
      </nav>
      <Suspense fallback={<p className="text-zinc-500">Načítám…</p>}>
        <Outlet />
      </Suspense>
    </>
  );
}

/** Old Rutina URLs (/habits?v=month&d=…) keep working. */
export function HabitsRedirect() {
  const { search } = useLocation();
  return <Navigate to={`/hero${search}`} replace />;
}
