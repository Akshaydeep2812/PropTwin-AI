import { ArrowRight, BadgeCheck, Building2, Search, ShieldCheck, TrendingUp } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { Card, ClaimBadge, PageHeader } from "../components/ui";

const GUIDES = [
  {
    id: "owner",
    icon: Building2,
    title: "Property owners",
    steps: [
      ["Register your property", "Under My properties, select Register a property. Add the built-up area, because the model needs it.", "/properties/new"],
      ["Get an AI estimate", "Open AI valuation and choose your property. You will get a value, a range, and what moved it.", "/valuations"],
      ["Create a digital twin", "From the property's page, open its twin. Every later change is kept as a version.", "/owner"],
      ["Test a what-if scenario", "In the twin, try a preset such as Market -10%. Your real record never changes.", "/simulator"],
      ["Get verified", "On the property's page, upload a document and request verification. A named verifier then decides.", "/owner"],
      ["Commit to the blockchain", "Store a hash of the record, so that later changes can be detected.", "/owner"],
    ],
  },
  {
    id: "investor",
    icon: TrendingUp,
    title: "Buyers and investors",
    steps: [
      ["Pick a locality", "Use Market insights to rank localities by yield and growth.", "/market"],
      ["Build a shortlist", "Browse listings, then select the heart icon to save a property.", "/properties"],
      ["Check the price", "Each property's Decision snapshot shows its asking price against the AI estimate and the locality.", "/properties"],
      ["Compare side by side", "Tick Compare on two to four listings. The best value in each row is highlighted.", "/properties"],
      ["Work out the returns", "Use Calculate returns on a property to see instalments and cash flow.", "/calculator"],
      ["Save a report", "Open the property's report and print it, or save it as a PDF.", "/properties"],
    ],
  },
  {
    id: "verifier",
    icon: BadgeCheck,
    title: "Verifiers",
    steps: [
      ["Open the queue", "Verification lists every request that is waiting for a decision.", "/verifier"],
      ["Read the documents", "Open the property to download what the owner submitted.", "/verifier"],
      ["Record a decision", "Approve or reject it with a note. The decision is kept against your name.", "/verifier"],
    ],
  },
  {
    id: "admin",
    icon: ShieldCheck,
    title: "Administrators",
    steps: [
      ["Activate a model", "Under Administration, then Models, approve a version that beat its baseline, and activate it.", "/admin"],
      ["Appoint verifiers", "Under Users, grant the verifier role to the right people.", "/admin"],
      ["Load market data", "Market insights reads the market observations table. The bundled seed script loads fictional data. To use real data, load a licensed source into that table with is_synthetic set to false.", "/market"],
      ["Watch system health", "Monitoring shows model drift, background jobs and blockchain status.", "/admin"],
    ],
  },
];

const GLOSSARY = [
  ["AI estimate", "What the model calculates from the inputs shown. It is not a sale price or a certified appraisal."],
  ["Estimate range", "Where the model expects most comparable values to fall. A 90% range was built to contain about 90 of 100 test values, and a wider range means less certainty."],
  ["Asking price check", "Compares the asking price with the estimate's range: below, inside or above. It does not say whether a property is a good buy."],
  ["Market index", "How a locality's prices moved relative to a starting point of 100. It shows change over time, not how expensive a locality is."],
  ["Price per sq ft", "Price divided by built-up area, which makes properties of different sizes comparable."],
  ["Gross rental yield", "A year's rent as a percentage of the price, before costs, vacancy and tax."],
  ["Cap rate", "A year's rent after vacancy and costs, as a percentage of the price. It ignores the loan."],
  ["Cash-on-cash return", "A year's cash flow after loan payments, as a percentage of the cash you put in."],
  ["Debt coverage", "Net rental income divided by loan payments. Below 1.00x, rent does not cover the loan."],
  ["EMI (instalment)", "The fixed monthly loan payment, which covers both interest and principal."],
  ["Digital twin", "A software copy of a property's record that keeps every past state. It has no sensors or live feed."],
  ["Scenario", "A what-if calculation from assumptions you choose. It is not a forecast, and it never changes the real record."],
  ["Verifier decision", "A named person reviewed the submitted files and recorded a decision. It is not a legal title search."],
  ["Salted hash", "A fingerprint of a record, mixed with a secret value. Anyone holding both can tell if the record changed, and the fingerprint reveals nothing by itself."],
  ["Blockchain-confirmed", "The transaction met the confirmation policy. It shows the record has not changed since then, not who legally owns the property."],
  ["Synthetic demo data", "Fictional records and market series used to demonstrate the product. They say nothing about real property."],
];

const FAQ = [
  ["Can I rely on an estimate to buy or sell?", "Not by itself. It is one input. The bundled model is trained on fictional data, so its figures only show how the product works. Before deciding, get a professional valuation and legal advice."],
  ["Why do I see \"No active model\"?", "An administrator has not activated a valuation model yet. The app shows this message rather than making up a figure."],
  ["Why can't I run a scenario on a listing?", "Scenarios run on a digital twin, and only a property's owner can create one. Save a listing that already has a twin, or ask its owner."],
  ["Who can see my street address and documents?", "You, administrators, and verifiers reviewing your request. Public listings never show the street address, and the blockchain only ever receives a hash."],
  ["Does a blockchain record prove I own the property?", "No. It shows that a record has not changed since it was committed. Legal ownership comes from your local land registry."],
  ["My estimate says it is out of date. What should I do?", "Details the estimate used, such as size or condition, have changed since it was made. Run a new one from AI valuation. Earlier estimates are always kept."],
  ["How do I become a verifier?", "An administrator grants that role. It cannot be chosen when you register."],
];

function Faq({ question, answer }) {
  return (
    <details className="group border-b border-slate-100 py-3 last:border-0">
      <summary className="cursor-pointer list-none font-medium text-navy-900 marker:hidden">{question}</summary>
      <p className="mt-1.5 text-sm text-slate-600">{answer}</p>
    </details>
  );
}

export default function HelpPage() {
  const { hash } = useLocation();
  const [query, setQuery] = useState("");
  const terms = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return needle ? GLOSSARY.filter(([term, meaning]) => `${term} ${meaning}`.toLowerCase().includes(needle)) : GLOSSARY;
  }, [query]);

  useEffect(() => {
    if (hash) document.getElementById(hash.slice(1))?.scrollIntoView?.();
  }, [hash]);

  return (
    <>
      <PageHeader title="Help center" subtitle="Step-by-step guides for your role, every term in plain language, and answers to common questions." />

      <h2 className="mb-3 text-lg font-semibold text-navy-900">Guides by role</h2>
      <div className="grid gap-4 md:grid-cols-2">
        {GUIDES.map(({ id, icon: Icon, title, steps }) => (
          <section key={id} id={id} aria-label={title} className="scroll-mt-20 rounded-xl border border-slate-200 bg-white p-5 shadow-card">
            <h3 className="flex items-center gap-2 font-semibold text-navy-900">
              <Icon aria-hidden className="h-4 w-4 text-brass-600" /> {title}
            </h3>
            <ol className="mt-3 space-y-3">
              {steps.map(([name, text, to], index) => (
                <li key={name} className="flex gap-3 text-sm">
                  <span className="tabular flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-slate-100 text-xs font-semibold text-navy-800">{index + 1}</span>
                  <span>
                    <Link to={to} className="inline-flex items-center gap-1 font-medium text-navy-900 hover:text-teal-700">
                      {name} <ArrowRight aria-hidden className="h-3 w-3" />
                    </Link>
                    <span className="block text-slate-600">{text}</span>
                  </span>
                </li>
              ))}
            </ol>
          </section>
        ))}
      </div>

      <h2 className="mb-3 mt-8 text-lg font-semibold text-navy-900">The four labels on every result</h2>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {[
          ["ai", "What a model calculated from the inputs shown."],
          ["hypothetical", "What your own assumptions lead to."],
          ["document", "What a named person decided after reviewing files."],
          ["chain", "That a record has not changed since it was committed."],
        ].map(([kind, text]) => (
          <div key={kind} className="rounded-xl border border-slate-200 bg-white p-4 shadow-card">
            <ClaimBadge kind={kind} />
            <p className="mt-2 text-sm text-slate-600">{text}</p>
          </div>
        ))}
      </div>

      <div className="mt-8 grid items-start gap-4 lg:grid-cols-2">
        <Card title="Glossary">
          <label className="relative block">
            <span className="sr-only">Search the glossary</span>
            <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search the glossary" className="w-full rounded-lg border border-slate-300 py-2 pl-9 pr-3 text-sm" />
          </label>
          <dl className="mt-4 space-y-3">
            {terms.map(([term, meaning]) => (
              <div key={term}>
                <dt className="text-sm font-medium text-navy-900">{term}</dt>
                <dd className="text-sm text-slate-600">{meaning}</dd>
              </div>
            ))}
            {terms.length === 0 && <p className="text-sm text-slate-600">No term matches that search.</p>}
          </dl>
        </Card>
        <Card title="Common questions">
          {FAQ.map(([question, answer]) => (
            <Faq key={question} question={question} answer={answer} />
          ))}
        </Card>
      </div>
    </>
  );
}
