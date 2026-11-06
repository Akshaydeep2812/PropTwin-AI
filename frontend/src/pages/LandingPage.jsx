import { ArrowRight, BadgeCheck, Blocks, Bot, Boxes, Calculator, CheckCircle2, Dices, FileCheck2, FileText, LineChart, Link2, Scale, Sparkles, Repeat } from "lucide-react";
import { Link, Navigate } from "react-router-dom";
import { DemoAccess } from "../components/guide";
import { useAuth } from "../hooks/useAuth";
import { BrandMark } from "../layouts/AppLayout";

const PATHS = [
  {
    title: "I own property",
    points: ["See what each property is estimated to be worth, with a range", "Test renovations and market changes before spending anything", "Keep a verified, tamper-evident record of every change"],
    cta: "Register a property",
    to: "/register",
  },
  {
    title: "I am buying or investing",
    points: ["Check any asking price against an AI estimate and its locality", "Compare up to four properties on yield and price per square foot", "Work out instalments and cash flow before making an offer"],
    cta: "Find a property",
    to: "/properties",
  },
  {
    title: "I am researching a market",
    points: ["Rank localities by price, 12-month change and rental yield", "Chart any two localities against each other", "No account needed"],
    cta: "See market insights",
    to: "/market",
  },
];

const FEATURES = [
  { icon: Sparkles, title: "AI valuation", text: "A value and a range for any property, the factors that moved it, and the model's stated limits." },
  { icon: Scale, title: "Asking price check", text: "See at a glance whether a price falls below, inside or above the estimate's range." },
  { icon: LineChart, title: "Market insights", text: "Median price, 12-month change, 5-year growth and rental yield for each locality." },
  { icon: Boxes, title: "Digital twin", text: "A software copy of the record that keeps every past state, with no risk to the original." },
  { icon: Repeat, title: "Scenario simulator", text: "Change market, renovation, rent or maintenance assumptions, then compare results side by side." },
  { icon: Calculator, title: "Investment calculator", text: "Instalments, cash flow, cap rate, break-even rent and an equity projection from your own assumptions." },
  { icon: BadgeCheck, title: "Document verification", text: "A named verifier reviews submitted files and records a decision. Listings show the resulting status." },
  { icon: Blocks, title: "Blockchain integrity check", text: "A salted hash on-chain means any later change to the record can be detected, and named." },
  { icon: FileText, title: "Printable property report", text: "One page with the estimate, price check, market context and trust status, ready to share or save as PDF." },
];

const CLAIMS = [
  { icon: Bot, title: "AI estimate", text: "A model's estimate from the inputs shown, with a range and its known limits. Not a sale price or a certified appraisal." },
  { icon: Dices, title: "Hypothetical simulation", text: "Your assumptions applied to a baseline with the formula shown. Not a forecast." },
  { icon: FileCheck2, title: "Verifier decision", text: "A named person reviewed the submitted files and recorded a decision. Not a legal title search." },
  { icon: Link2, title: "Blockchain-confirmed", text: "Proof that a record has not changed since it was committed. Not proof of legal ownership." },
];

const STEPS = [
  ["Register a property", "Record its characteristics, renovation history and documents."],
  ["Get an estimate", "A trained model values it, and shows what moved the number."],
  ["Create its digital twin", "A software copy keeps every past state, so you can test scenarios without touching the real record."],
  ["Commit it to a blockchain", "A salted hash goes on-chain, so that any later change to the record can be detected."],
];

/** A picture of the product's main result. Its figures are invented for illustration, and it says so. */
function SampleReport() {
  return (
    <figure aria-label="Sample estimate with invented figures" className="rounded-2xl border border-white/15 bg-white p-5 text-navy-900 shadow-2xl">
      <figcaption className="flex items-center justify-between gap-2">
        <span className="text-xs font-semibold uppercase tracking-widest text-brass-600">Sample result</span>
        <span className="rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-medium text-amber-900">Invented figures</span>
      </figcaption>
      <p className="mt-4 text-sm text-slate-600">Estimated market value</p>
      <p className="figure text-4xl sm:text-5xl">₹1,24,00,000</p>
      <p className="tabular mt-1 text-sm text-slate-600">90% range: ₹1.09 Cr to ₹1.39 Cr</p>
      <div className="relative mt-8 h-2 rounded-full bg-slate-100">
        <div className="absolute inset-y-0 left-[18%] right-[18%] rounded-full bg-teal-600/30" />
        <div className="absolute left-1/2 top-1/2 h-3.5 w-0.5 -translate-y-1/2 rounded bg-teal-700" />
        <div className="absolute left-[68%] top-1/2 -translate-x-1/2 -translate-y-1/2">
          <span className="absolute bottom-3 left-1/2 -translate-x-1/2 rounded bg-navy-900 px-1.5 py-0.5 text-[10px] font-medium text-white">Asking</span>
          <span className="block h-3.5 w-3.5 rounded-full border-2 border-white bg-navy-900 shadow" />
        </div>
      </div>
      <ul className="mt-5 space-y-2 text-sm text-slate-700">
        <li className="flex gap-2"><CheckCircle2 aria-hidden className="mt-0.5 h-4 w-4 shrink-0 text-teal-700" /> Asking price is inside the estimate's range</li>
        <li className="flex gap-2"><CheckCircle2 aria-hidden className="mt-0.5 h-4 w-4 shrink-0 text-teal-700" /> Gross yield is above the locality's</li>
        <li className="flex gap-2"><CheckCircle2 aria-hidden className="mt-0.5 h-4 w-4 shrink-0 text-teal-700" /> Documents reviewed by a named verifier</li>
      </ul>
    </figure>
  );
}

export default function LandingPage() {
  const { user, loading } = useAuth();
  if (!loading && user) return <Navigate to="/dashboard" replace />;
  return (
    <div className="bg-white">
      <div className="hero-backdrop text-white">
        <nav aria-label="Primary" className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-4 py-4 lg:px-8">
          <span className="flex items-center gap-2.5">
            <BrandMark />
            <span className="font-display text-lg font-medium tracking-tight">PropTwin AI</span>
          </span>
          <div className="flex items-center gap-1 text-sm font-medium">
            <Link to="/properties" className="hidden px-3 py-2 text-slate-200 hover:text-white sm:block">Browse</Link>
            <Link to="/market" className="hidden px-3 py-2 text-slate-200 hover:text-white sm:block">Markets</Link>
            <Link to="/help" className="hidden px-3 py-2 text-slate-200 hover:text-white sm:block">Help</Link>
            <Link to="/login" className="px-3 py-2 text-slate-200 hover:text-white">Sign in</Link>
          </div>
        </nav>
        <div className="mx-auto grid max-w-6xl items-center gap-12 px-4 pb-20 pt-12 lg:grid-cols-[1.15fr_1fr] lg:px-8 lg:pt-16">
          <div>
            <h1 className="text-4xl leading-[1.08] sm:text-6xl">Know what a property is worth, and exactly how far to trust that number.</h1>
            <p className="mt-6 max-w-xl text-lg text-slate-300">Value a property, check an asking price, test what-if scenarios, and keep a tamper-evident record. Every result says what it is, and what it is not.</p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link to="/register" className="inline-flex items-center gap-2 rounded-lg bg-teal-600 px-5 py-3 font-medium text-white shadow-lg hover:bg-teal-700">
                Create an account <ArrowRight aria-hidden className="h-4 w-4" />
              </Link>
              <Link to="/properties" className="rounded-lg border border-white/30 px-5 py-3 font-medium text-white hover:bg-white/10">
                Explore listings
              </Link>
            </div>
            <div className="mt-8 max-w-xl">
              <DemoAccess tone="dark" heading="Try it now, without signing up" />
            </div>
          </div>
          <SampleReport />
        </div>
      </div>

      <section className="mx-auto max-w-6xl px-4 py-16 lg:px-8">
        <h2 className="font-display text-3xl font-medium tracking-tight text-navy-900">Start from what you need</h2>
        <div className="mt-8 grid gap-5 md:grid-cols-3">
          {PATHS.map((path) => (
            <div key={path.title} className="flex flex-col rounded-xl border border-slate-200 bg-slate-50 p-6">
              <h3 className="text-lg font-semibold text-navy-900">{path.title}</h3>
              <ul className="mt-4 flex-1 space-y-2.5 text-sm text-slate-700">
                {path.points.map((point) => (
                  <li key={point} className="flex gap-2">
                    <CheckCircle2 aria-hidden className="mt-0.5 h-4 w-4 shrink-0 text-teal-700" /> {point}
                  </li>
                ))}
              </ul>
              <Link to={path.to} className="mt-5 inline-flex items-center gap-1.5 text-sm font-semibold text-teal-700">
                {path.cta} <ArrowRight aria-hidden className="h-4 w-4" />
              </Link>
            </div>
          ))}
        </div>
      </section>

      <section className="bg-slate-50">
        <div className="mx-auto max-w-6xl px-4 py-16 lg:px-8">
          <h2 className="font-display text-3xl font-medium tracking-tight text-navy-900">What you can do</h2>
          <div className="mt-8 grid gap-x-8 gap-y-7 sm:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map(({ icon: Icon, title, text }) => (
              <div key={title} className="flex gap-3.5">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-white text-teal-700 shadow-card">
                  <Icon aria-hidden className="h-[18px] w-[18px]" />
                </span>
                <div>
                  <h3 className="font-semibold text-navy-900">{title}</h3>
                  <p className="mt-1 text-sm text-slate-600">{text}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-4 py-16 lg:px-8">
        <h2 className="font-display text-3xl font-medium tracking-tight text-navy-900">How it works</h2>
        <ol className="mt-8 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {STEPS.map(([title, text], index) => (
            <li key={title} className="border-t-2 border-teal-700 pt-4">
              <span className="figure text-2xl text-brass-600">{index + 1}</span>
              <h3 className="mt-1 font-semibold text-navy-900">{title}</h3>
              <p className="mt-1 text-sm text-slate-600">{text}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="bg-navy-950 text-white">
        <div className="mx-auto max-w-6xl px-4 py-16 lg:px-8">
          <h2 className="font-display text-3xl font-medium tracking-tight">Four kinds of claim, never blurred</h2>
          <p className="mt-2 max-w-2xl text-slate-300">Property decisions are expensive. Each result carries a label saying what it is and what it does not mean.</p>
          <div className="mt-8 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
            {CLAIMS.map(({ icon: Icon, title, text }) => (
              <div key={title}>
                <Icon aria-hidden className="h-6 w-6 text-teal-100" />
                <h3 className="mt-3 font-semibold">{title}</h3>
                <p className="mt-1 text-sm text-slate-300">{text}</p>
              </div>
            ))}
          </div>
          <div className="mt-10 flex flex-wrap gap-3">
            <Link to="/register" className="rounded-lg bg-teal-600 px-5 py-3 font-medium text-white hover:bg-teal-700">Get started</Link>
            <Link to="/help" className="rounded-lg border border-white/30 px-5 py-3 font-medium text-white hover:bg-white/10">Read the guide</Link>
          </div>
        </div>
      </section>

      <footer className="mx-auto max-w-6xl px-4 py-8 text-sm text-slate-500 lg:px-8">
        Valuations are statistical estimates. A blockchain record does not establish legal ownership or prove that documents are authentic.
      </footer>
    </div>
  );
}
