import { Bell, Blocks, Building2, Calculator, Gauge, Heart, HelpCircle, History, LayoutDashboard, LineChart, LogOut, Menu, Repeat, Search, Shield, ShieldCheck, Sparkles, User, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { Button, Spinner } from "../components/ui";
import { useAuth } from "../hooks/useAuth";
import { useAsync } from "../hooks/useAsync";
import { api } from "../services/api";

/** Hiding a link is only a convenience. The API enforces every one of these permissions on its own. */
export const NAV_ITEMS = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard, group: "Overview" },
  { to: "/owner", label: "My properties", icon: Gauge, roles: ["owner", "admin"], group: "Overview" },
  { to: "/investor", label: "Investments", icon: Heart, roles: ["investor"], group: "Overview" },
  { to: "/properties", label: "Properties", icon: Building2, public: true, group: "Explore" },
  { to: "/market", label: "Market insights", icon: LineChart, public: true, group: "Explore" },
  { to: "/valuations", label: "AI valuation", icon: Sparkles, group: "Analyze" },
  { to: "/valuations/history", label: "Valuation history", icon: History, group: "Analyze" },
  { to: "/simulator", label: "Scenario simulator", icon: Repeat, roles: ["owner", "investor", "admin"], group: "Analyze" },
  { to: "/calculator", label: "Investment calculator", icon: Calculator, public: true, group: "Analyze" },
  { to: "/transfers", label: "Transfers", icon: Blocks, group: "Records" },
  { to: "/verifier", label: "Verification", icon: ShieldCheck, roles: ["verifier", "admin"], group: "Records" },
  { to: "/admin", label: "Administration", icon: Shield, roles: ["admin"], group: "Records" },
  { to: "/help", label: "Help center", icon: HelpCircle, public: true, group: "Support" },
];

export function navItemsFor(user) {
  return NAV_ITEMS.filter((item) => {
    if (!user) return item.public;
    return !item.roles || item.roles.some((role) => user.roles.includes(role));
  });
}

function NavItems({ user, onNavigate }) {
  const items = navItemsFor(user);
  const groups = [...new Set(items.map((item) => item.group))];
  return (
    <nav aria-label="Main" className="flex flex-1 flex-col gap-5">
      {groups.map((group) => (
        <div key={group}>
          <p className="mb-1 px-3 text-[11px] font-semibold uppercase tracking-widest text-slate-400">{group}</p>
          <div className="flex flex-col gap-0.5">
            {items
              .filter((item) => item.group === group)
              .map(({ to, label, icon: Icon }) => (
                <NavLink
                  key={to}
                  to={to}
                  end={to === "/valuations" || to === "/properties"}
                  onClick={onNavigate}
                  className={({ isActive }) => `flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${isActive ? "bg-white/10 text-white shadow-[inset_2px_0_0_var(--color-teal-600)]" : "text-slate-300 hover:bg-white/5 hover:text-white"}`}
                >
                  <Icon aria-hidden className="h-4 w-4" />
                  {label}
                </NavLink>
              ))}
          </div>
        </div>
      ))}
    </nav>
  );
}

export function BrandMark({ className = "h-7 w-7" }) {
  return (
    <svg aria-hidden viewBox="0 0 32 32" className={className}>
      <rect width="32" height="32" rx="8" fill="#0d9488" />
      <path d="M8 24V12l6-4v16M18 24V8l6 4v12" fill="none" stroke="#fff" strokeWidth="2.2" strokeLinejoin="round" strokeLinecap="round" />
      <path d="M6 24h20" stroke="#dcc48f" strokeWidth="2.2" strokeLinecap="round" />
    </svg>
  );
}

function Brand() {
  return (
    <Link to="/" className="flex items-center gap-2.5 px-1 text-white">
      <BrandMark />
      <span className="font-display text-lg font-medium tracking-tight">PropTwin AI</span>
    </Link>
  );
}

function NotificationBell() {
  const unread = useAsync(() => api.notifications.list({ unread_only: true, page_size: 1 }), []);
  const count = unread.data?.total ?? 0;
  return (
    <Link to="/profile#notifications" aria-label={`Notifications: ${count} unread`} className="relative rounded-lg p-2 text-slate-600 hover:bg-slate-100">
      <Bell aria-hidden className="h-5 w-5" />
      {count > 0 && <span className="absolute right-0.5 top-0.5 min-w-4 rounded-full bg-teal-700 px-1 text-center text-[10px] font-semibold text-white">{count}</span>}
    </Link>
  );
}

function QuickSearch() {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  return (
    <form
      role="search"
      className="relative hidden max-w-sm flex-1 md:block"
      onSubmit={(event) => {
        event.preventDefault();
        navigate(query.trim() ? `/properties?q=${encodeURIComponent(query.trim())}` : "/properties");
      }}
    >
      <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
      <input type="search" aria-label="Find listings" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Find listings by title, locality or city" className="w-full rounded-lg border border-slate-200 bg-slate-50 py-2 pl-9 pr-3 text-sm placeholder:text-slate-500 hover:border-slate-300" />
    </form>
  );
}

export default function AppLayout() {
  const { user, loading, logout } = useAuth();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const [open, setOpen] = useState(false);

  useEffect(() => {
    window.scrollTo?.(0, 0);
  }, [pathname]);

  // Pages load their data as soon as they mount. Until the session is restored they would ask as a guest,
  // so a signed-in owner reloading their own draft would be told it does not exist.
  if (loading) return <Spinner label="Restoring your session" />;

  return (
    <div className="min-h-screen lg:flex">
      <aside className="sticky top-0 hidden h-screen w-64 shrink-0 flex-col gap-7 overflow-y-auto bg-navy-950 p-4 lg:flex print:hidden">
        <Brand />
        <NavItems user={user} />
      </aside>

      {open && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-navy-950/50" onClick={() => setOpen(false)} aria-hidden />
          <aside className="relative flex h-full w-72 flex-col gap-7 overflow-y-auto bg-navy-950 p-4">
            <div className="flex items-center justify-between">
              <Brand />
              <button type="button" aria-label="Close menu" onClick={() => setOpen(false)} className="text-slate-300">
                <X aria-hidden className="h-5 w-5" />
              </button>
            </div>
            <NavItems user={user} onNavigate={() => setOpen(false)} />
          </aside>
        </div>
      )}

      <div className="min-w-0 flex-1">
        {user?.is_demo && (
          <p className="bg-brass-100 px-4 py-1.5 text-center text-xs text-navy-900 print:hidden">
            You are exploring a demo account, and everything in it is fictional.{" "}
            <button
              type="button"
              className="font-medium underline"
              onClick={async () => {
                await logout();
                navigate("/register");
              }}
            >
              Create your own account
            </button>
          </p>
        )}
        <header className="sticky top-0 z-20 flex items-center gap-3 border-b border-slate-200 bg-white/90 px-4 py-2.5 backdrop-blur lg:px-8 print:hidden">
          <button type="button" aria-label="Open menu" onClick={() => setOpen(true)} className="text-navy-900 lg:hidden">
            <Menu aria-hidden className="h-6 w-6" />
          </button>
          <QuickSearch />
          <div className="ml-auto flex items-center gap-2">
            {user ? (
              <>
                <NotificationBell />
                <Link to="/profile" className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-sm font-medium text-navy-900 hover:bg-slate-100">
                  <User aria-hidden className="h-4 w-4" />
                  <span className="hidden sm:inline">{user.display_name}</span>
                </Link>
                <Button
                  variant="ghost"
                  onClick={async () => {
                    await logout();
                    navigate("/");
                  }}
                >
                  <LogOut aria-hidden className="h-4 w-4" />
                  <span className="hidden sm:inline">Sign out</span>
                </Button>
              </>
            ) : (
              <>
                <Link to="/login" className="px-3 py-2 text-sm font-medium text-navy-800">
                  Sign in
                </Link>
                <Link to="/register" className="rounded-lg bg-teal-700 px-3 py-2 text-sm font-medium text-white shadow-sm hover:bg-teal-600">
                  Create account
                </Link>
              </>
            )}
          </div>
        </header>
        <main key={pathname} className="page-enter mx-auto max-w-6xl px-4 py-7 lg:px-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
