import { ArrowRight, CheckCircle2, ChevronDown, Circle, Compass, HelpCircle, PartyPopper, UserRound, X } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAsync } from "../hooks/useAsync";
import { useAuth } from "../hooks/useAuth";
import { api } from "../services/api";
import { ErrorNote } from "./ui";

function readFlag(key) {
  try {
    return localStorage.getItem(key) === "1";
  } catch {
    return false;
  }
}

function writeFlag(key, value) {
  try {
    if (value) localStorage.setItem(key, "1");
    else localStorage.removeItem(key);
  } catch {
    // Storage can be blocked. The preference then lasts only until the page reloads.
  }
}

/** Plain-language explanation of one term, opened by hover, focus or tap. */
export function InfoTip({ label, children }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const box = useRef(null);
  useEffect(() => {
    if (!open) return undefined;
    const close = (event) => {
      if (!box.current?.contains(event.target)) setOpen(false);
    };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, [open]);
  return (
    <span ref={box} className="relative inline-flex align-middle print:hidden" onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
      <button
        type="button"
        aria-label={`What is ${label}?`}
        aria-expanded={open}
        aria-describedby={open ? id : undefined}
        onClick={() => setOpen((value) => !value)}
        onKeyDown={(event) => event.key === "Escape" && setOpen(false)}
        className="rounded-full text-slate-400 hover:text-teal-700"
      >
        <HelpCircle aria-hidden className="h-3.5 w-3.5" />
      </button>
      {open && (
        <span id={id} role="tooltip" className="absolute bottom-full left-1/2 z-30 mb-2 w-60 -translate-x-1/2 rounded-lg bg-navy-900 px-3 py-2 text-left text-xs font-normal normal-case leading-relaxed tracking-normal text-white shadow-lg">
          {children}
        </span>
      )}
    </span>
  );
}

/** A short "how to use this page" panel. New users see it open; once dismissed it stays a small link. */
export function PageGuide({ id, title = "How to use this page", steps, note }) {
  const key = `proptwin_guide_${id}`;
  const [collapsed, setCollapsed] = useState(() => readFlag(key));
  const toggle = (next) => {
    setCollapsed(next);
    writeFlag(key, next);
  };
  if (collapsed) {
    return (
      <button type="button" onClick={() => toggle(false)} className="mb-4 inline-flex items-center gap-1.5 text-sm font-medium text-teal-700 print:hidden">
        <Compass aria-hidden className="h-4 w-4" /> {title} <ChevronDown aria-hidden className="h-3.5 w-3.5" />
      </button>
    );
  }
  return (
    <aside aria-label={title} className="mb-5 rounded-xl border border-brass-300/60 bg-brass-100/50 p-4 print:hidden">
      <div className="flex items-start justify-between gap-3">
        <p className="flex items-center gap-2 text-sm font-semibold text-navy-900">
          <Compass aria-hidden className="h-4 w-4 text-brass-600" /> {title}
        </p>
        <button type="button" onClick={() => toggle(true)} aria-label="Hide this guide" className="text-slate-500 hover:text-navy-900">
          <X aria-hidden className="h-4 w-4" />
        </button>
      </div>
      <ol className="mt-3 grid gap-3 sm:grid-cols-3">
        {steps.map((step, index) => (
          <li key={step} className="flex gap-2.5 text-sm text-slate-700">
            <span className="tabular flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-white text-xs font-semibold text-brass-600 ring-1 ring-brass-300">{index + 1}</span>
            <span>{step}</span>
          </li>
        ))}
      </ol>
      {note && <p className="mt-3 text-xs text-slate-600">{note}</p>}
    </aside>
  );
}

const ROLE_INTRO = {
  owner: "Take one property through the whole journey. Each step ticks itself when it is really done.",
  investor: "Build a shortlist, check its prices, and test what could change. Each step ticks itself when it is really done.",
  verifier: "Your job is to review submitted documents and record a decision against your name.",
  admin: "These are what the platform needs before everyone else can use it.",
};

/** The role's checklist. It is driven by the API from real records, so it cannot show progress that did not happen. */
export function GettingStarted({ onboarding }) {
  const key = `proptwin_getting_started_${onboarding?.role}`;
  const [dismissed, setDismissed] = useState(() => readFlag(key));
  if (!onboarding || dismissed) return null;
  const { steps, completed, total, role } = onboarding;
  const finished = completed === total;
  const next = steps.find((step) => !step.done);
  const hide = () => {
    setDismissed(true);
    writeFlag(key, true);
  };
  return (
    <section aria-label="Getting started" className="overflow-hidden rounded-xl bg-navy-900 text-white shadow-lift">
      <div className="hero-backdrop p-5 sm:p-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="flex items-center gap-2 text-lg font-semibold">
              {finished && <PartyPopper aria-hidden className="h-5 w-5 text-brass-300" />}
              {finished ? "You have completed every step" : "Getting started"}
            </h2>
            <p className="mt-1 max-w-2xl text-sm text-slate-300">{finished ? "Everything below stays available from the menu." : ROLE_INTRO[role]}</p>
          </div>
          <button type="button" onClick={hide} aria-label="Hide getting started" className="text-slate-300 hover:text-white">
            <X aria-hidden className="h-5 w-5" />
          </button>
        </div>
        <div className="mt-4 flex items-center gap-3">
          <div role="progressbar" aria-label="Steps completed" aria-valuemin={0} aria-valuemax={total} aria-valuenow={completed} className="h-1.5 flex-1 overflow-hidden rounded-full bg-white/15">
            <div className="h-full rounded-full bg-teal-600 transition-all" style={{ width: `${(completed * 100) / total}%` }} />
          </div>
          <span className="tabular text-xs font-medium text-slate-300">
            {completed} of {total} done
          </span>
        </div>
        <ul className="mt-5 grid items-start gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {steps.map((step) => {
            const isNext = step.key === next?.key;
            return (
              <li key={step.key} className={`flex flex-col rounded-lg p-3 ${isNext ? "bg-white text-navy-900" : "bg-white/[0.06]"}`}>
                <p className="flex items-center gap-2 text-sm font-semibold">
                  {step.done ? <CheckCircle2 aria-label="Done" className="h-4 w-4 shrink-0 text-teal-600" /> : <Circle aria-label="Not done yet" className={`h-4 w-4 shrink-0 ${isNext ? "text-teal-700" : "text-slate-400"}`} />}
                  <span className={step.done ? "text-slate-300" : ""}>{step.title}</span>
                </p>
                {!step.done && <p className={`mt-1 flex-1 text-xs leading-relaxed ${isNext ? "text-slate-600" : "text-slate-300"}`}>{step.description}</p>}
                {isNext && (
                  <Link to={step.href} className="mt-2.5 inline-flex items-center gap-1.5 self-start rounded-lg bg-teal-700 px-3 py-1.5 text-xs font-semibold text-white hover:bg-teal-600">
                    {step.cta} <ArrowRight aria-hidden className="h-3.5 w-3.5" />
                  </Link>
                )}
              </li>
            );
          })}
        </ul>
      </div>
    </section>
  );
}

const DEMO_ROLES = {
  owner: { label: "Property owner", blurb: "Portfolio, estimates, twins" },
  investor: { label: "Investor", blurb: "Shortlist, price checks, yields" },
  verifier: { label: "Verifier", blurb: "Review queue and decisions" },
  admin: { label: "Administrator", blurb: "Models, users, monitoring" },
};

const DEMO_ORDER = ["owner", "investor", "verifier", "admin"];

function demoRole(account) {
  return account.roles.includes("admin") ? "admin" : account.roles[0];
}

/** One-click demo sign-in. The API returns no accounts unless demo login is switched on, so this then renders nothing. */
export function DemoAccess({ tone = "light", heading = "Or look around first" }) {
  const accounts = useAsync(() => api.auth.demoAccounts(), []);
  const { demoLogin } = useAuth();
  const navigate = useNavigate();
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);
  if (!Array.isArray(accounts.data) || accounts.data.length === 0) return null;
  const dark = tone === "dark";
  const open = async (account) => {
    setBusy(account.email);
    setError(null);
    try {
      await demoLogin(account.email);
      navigate("/dashboard", { replace: true });
    } catch (caught) {
      setError(caught);
      setBusy(null);
    }
  };
  return (
    <div>
      <p className={`text-sm font-medium ${dark ? "text-slate-200" : "text-navy-800"}`}>{heading}</p>
      <p className={`mt-0.5 text-xs ${dark ? "text-slate-300" : "text-slate-600"}`}>Open a ready-filled demo account. All of its data is fictional, and no password is needed.</p>
      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        {[...accounts.data].sort((a, b) => DEMO_ORDER.indexOf(demoRole(a)) - DEMO_ORDER.indexOf(demoRole(b))).map((account) => {
          const role = DEMO_ROLES[demoRole(account)] ?? { label: account.display_name, blurb: "" };
          return (
            <button
              key={account.email}
              type="button"
              disabled={Boolean(busy)}
              onClick={() => open(account)}
              className={`flex items-center gap-2.5 rounded-lg border px-3 py-2 text-left transition-colors disabled:opacity-60 ${dark ? "border-white/20 bg-white/[0.06] text-white hover:bg-white/[0.12]" : "border-slate-200 bg-white text-navy-900 hover:border-teal-600"}`}
            >
              <UserRound aria-hidden className={`h-4 w-4 shrink-0 ${dark ? "text-teal-100" : "text-teal-700"}`} />
              <span className="min-w-0">
                <span className="block text-sm font-medium">{busy === account.email ? "Opening…" : `Explore as ${role.label}`}</span>
                <span className={`block truncate text-xs ${dark ? "text-slate-300" : "text-slate-500"}`}>{role.blurb}</span>
              </span>
            </button>
          );
        })}
      </div>
      {error && (
        <div className="mt-3">
          <ErrorNote error={error} />
        </div>
      )}
    </div>
  );
}
