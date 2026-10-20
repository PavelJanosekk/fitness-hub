import { Bot, Dumbbell, Footprints, LayoutDashboard, Settings, Swords, Utensils } from "lucide-react";
import { NavLink, Outlet } from "react-router";
import { LevelWatcher } from "./rpg/LevelWatcher";

const NAV = [
  { to: "/", label: "Přehled", icon: LayoutDashboard },
  { to: "/gym", label: "Gym", icon: Dumbbell },
  { to: "/run", label: "Běh", icon: Footprints },
  { to: "/nutrition", label: "Jídlo", icon: Utensils },
  { to: "/hero", label: "Hrdina", icon: Swords },
  { to: "/coach", label: "Kouč", icon: Bot },
] as const;

/** Phone: content + fixed bottom tab bar (safe-area aware). Desktop (md+): sidebar. */
export function Layout() {
  return (
    <div className="min-h-dvh md:flex">
      <aside className="hidden md:flex md:w-56 md:flex-col md:gap-1 md:border-r md:border-zinc-800 md:p-4">
        <div className="mb-4 px-3 text-lg font-semibold">Fitness Hub</div>
        {[...NAV, { to: "/settings", label: "Nastavení", icon: Settings }].map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-lg px-3 py-2 text-sm ${isActive ? "bg-zinc-800 text-zinc-50" : "text-zinc-400 hover:bg-zinc-900"}`
            }
          >
            <Icon size={18} /> {label}
          </NavLink>
        ))}
      </aside>

      <main className="pt-safe mx-auto w-full max-w-3xl px-4 pb-28 md:pb-8">
        <Outlet />
      </main>
      <LevelWatcher />

      <nav className="ui-tabbar fixed z-30 md:hidden">
        <div className="grid grid-cols-6">
          {NAV.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              className="ui-tab flex flex-col items-center gap-1 py-2.5 text-[11px]"
            >
              <Icon size={22} strokeWidth={2} />
              {label}
            </NavLink>
          ))}
        </div>
      </nav>
    </div>
  );
}

/** Page header; `action` sits on the right (e.g. the settings gear on phones). */
export function PageHeader({ title, action }: { title: string; action?: React.ReactNode }) {
  return (
    <header className="flex items-center justify-between py-4">
      <h1 className="ui-title">{title}</h1>
      {action}
    </header>
  );
}

export function Card({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <section className={`ui-card p-4 ${className}`}>{children}</section>;
}
