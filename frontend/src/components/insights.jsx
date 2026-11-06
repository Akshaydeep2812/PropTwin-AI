import { ArrowRight, Blocks, Boxes, CheckCircle2, ClipboardCheck, FilePlus2, Info, Sparkles, ThumbsUp, TriangleAlert } from "lucide-react";
import { Link } from "react-router-dom";
import { compactMoney, date, money, percent, plainPercent } from "../utils/format";
import { InfoTip } from "./guide";
import { ClaimBadge, SyntheticBadge } from "./ui";

const POSITION = {
  below_range: { label: "Below the estimate's range", className: "bg-teal-100 text-teal-700" },
  within_range: { label: "Inside the estimate's range", className: "bg-slate-100 text-slate-700" },
  above_range: { label: "Above the estimate's range", className: "bg-amber-100 text-amber-900" },
};

export function PricePositionBadge({ position }) {
  const style = POSITION[position];
  if (!style) return null;
  return <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${style.className}`}>{style.label}</span>;
}

/** Where the asking price sits against the estimate's range. The numbers are always written out beside the marks. */
export function RangeBar({ lower, value, upper, asking, currency }) {
  const low = Number(lower);
  const high = Number(upper);
  const mid = Number(value);
  const ask = asking === null || asking === undefined ? null : Number(asking);
  const points = [low, high, mid, ...(ask === null ? [] : [ask])];
  const min = Math.min(...points);
  const max = Math.max(...points);
  const pad = (max - min) * 0.12 || max * 0.05;
  const at = (point) => `${((point - (min - pad)) * 100) / (max - min + 2 * pad)}%`;
  return (
    <div>
      <div className="relative mt-7 h-2 rounded-full bg-slate-100">
        <div className="absolute h-full rounded-full bg-teal-600/30" style={{ left: at(low), width: `calc(${at(high)} - ${at(low)})` }} />
        <div aria-hidden className="absolute top-1/2 h-3.5 w-0.5 -translate-x-1/2 -translate-y-1/2 rounded bg-teal-700" style={{ left: at(mid) }} />
        {ask !== null && (
          <div className="absolute top-1/2 -translate-x-1/2 -translate-y-1/2" style={{ left: at(ask) }}>
            <span className="absolute bottom-3 left-1/2 -translate-x-1/2 whitespace-nowrap rounded bg-navy-900 px-1.5 py-0.5 text-[10px] font-medium text-white">Asking</span>
            <span className="block h-3.5 w-3.5 rounded-full border-2 border-white bg-navy-900 shadow" />
          </div>
        )}
      </div>
      <dl className="tabular mt-2.5 grid grid-cols-3 gap-2 text-xs">
        <div>
          <dt className="text-slate-500">Range low</dt>
          <dd className="font-medium text-navy-900">{compactMoney(low, currency)}</dd>
        </div>
        <div className="text-center">
          <dt className="text-slate-500">Estimate</dt>
          <dd className="font-medium text-teal-700">{compactMoney(mid, currency)}</dd>
        </div>
        <div className="text-right">
          <dt className="text-slate-500">Range high</dt>
          <dd className="font-medium text-navy-900">{compactMoney(high, currency)}</dd>
        </div>
      </dl>
    </div>
  );
}

function Metric({ label, tip, value, compare }) {
  return (
    <div className="rounded-lg bg-slate-50 p-3.5">
      <p className="flex items-center gap-1.5 text-xs font-medium text-slate-600">
        {label} {tip && <InfoTip label={label}>{tip}</InfoTip>}
      </p>
      <p className="figure mt-1 text-xl text-navy-900">{value}</p>
      {compare && <p className="mt-0.5 text-xs text-slate-600">{compare}</p>}
    </div>
  );
}

const TONES = {
  positive: { icon: ThumbsUp, className: "text-teal-700", label: "In its favour" },
  caution: { icon: TriangleAlert, className: "text-amber-700", label: "Worth checking" },
  neutral: { icon: Info, className: "text-slate-500", label: "For context" },
};

/** The plain-language summary at the top of a property page: is this price reasonable, and how far can the record be trusted? */
export function DecisionSnapshot({ insights, propertyId, signedIn }) {
  if (!insights) return null;
  const { estimate, currency, market } = insights;
  const synthetic = estimate?.trained_on_synthetic_data || market?.is_synthetic;
  return (
    <section aria-labelledby="snapshot-heading" className="rounded-xl border border-slate-200 bg-white p-5 shadow-card sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="snapshot-heading" className="text-base font-semibold text-navy-900">Decision snapshot</h2>
        <div className="flex flex-wrap items-center gap-2">
          {synthetic && <SyntheticBadge />}
          <PricePositionBadge position={insights.price_position} />
        </div>
      </div>
      <div className="mt-4 grid gap-5 lg:grid-cols-5">
        <div className="lg:col-span-3">
          <div className="rounded-lg border border-slate-200 p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="flex items-center gap-1.5 text-xs font-medium text-slate-600">
                Asking price against the AI estimate
                <InfoTip label="the estimate's range">The range is where the model expects most comparable values to fall. A figure outside it differs from the model by more than its usual error.</InfoTip>
              </p>
              <ClaimBadge kind="ai" />
            </div>
            {estimate ? (
              <>
                <RangeBar lower={estimate.lower} value={estimate.value} upper={estimate.upper} asking={insights.asking_price} currency={currency} />
                {insights.asking_vs_estimate_pct !== null && (
                  <p className="mt-3 text-sm text-slate-700">
                    The asking price of <span className="tabular font-medium text-navy-900">{money(insights.asking_price, currency)}</span> is <span className="tabular font-medium text-navy-900">{plainPercent(Math.abs(Number(insights.asking_vs_estimate_pct)), 1)}</span> {Number(insights.asking_vs_estimate_pct) >= 0 ? "above" : "below"} the estimate.
                  </p>
                )}
                <p className="mt-1 text-xs text-slate-500">
                  Estimated {date(estimate.predicted_at)}
                  {!estimate.is_current && " · out of date: the details it used have since changed"}
                </p>
              </>
            ) : (
              <p className="mt-3 text-sm text-slate-600">
                No estimate has been made for this property yet.{" "}
                {signedIn && (
                  <Link className="font-medium text-teal-700 underline" to={`/valuations?property=${propertyId}`}>
                    Get one now
                  </Link>
                )}
              </p>
            )}
          </div>
          <div className="mt-3 grid gap-3 sm:grid-cols-3">
            <Metric
              label="Price per sq ft"
              tip="Asking price divided by built-up area. It lets you compare properties of different sizes."
              value={insights.asking_per_sqft ? money(insights.asking_per_sqft, currency) : "Not available"}
              compare={insights.market_per_sqft && `Locality median ${money(insights.market_per_sqft, currency)}`}
            />
            <Metric
              label="Gross rental yield"
              tip="A year's rent as a percentage of the asking price, before costs, vacancy and tax."
              value={insights.gross_yield_pct ? plainPercent(insights.gross_yield_pct) : "Not available"}
              compare={insights.market_yield_pct && `Locality ${plainPercent(insights.market_yield_pct)}`}
            />
            <Metric
              label="Locality, 12 months"
              tip="Change in the locality's price index over the last 12 months. It describes the past, not the future."
              value={market?.change_12m_pct ? percent(market.change_12m_pct, 1) : "Not available"}
              compare={market && `${market.locality}, to ${date(market.latest_period)}`}
            />
          </div>
        </div>
        <div className="lg:col-span-2">
          <h3 className="text-sm font-semibold text-navy-900">What stands out</h3>
          <ul className="mt-2 space-y-2.5">
            {insights.takeaways.map((note) => {
              const { icon: Icon, className, label } = TONES[note.tone];
              return (
                <li key={note.text} className="flex gap-2 text-sm text-slate-700">
                  <Icon role="img" aria-label={label} className={`mt-0.5 h-4 w-4 shrink-0 ${className}`} />
                  <span>{note.text}</span>
                </li>
              );
            })}
          </ul>
        </div>
      </div>
      <p className="mt-4 border-t border-slate-100 pt-3 text-xs text-slate-500">{insights.disclaimer}</p>
    </section>
  );
}

/** The owner's view of how far this property has come, and the one thing to do next. */
export function PropertyJourney({ insights, propertyId }) {
  if (!insights) return null;
  const { status, completeness } = insights;
  const verified = status.verification_status === "verified";
  const steps = [
    { label: "Registered", icon: FilePlus2, done: true, href: `/properties/${propertyId}/edit`, cta: "Edit details" },
    { label: status.has_estimate && !status.estimate_current ? "Estimate out of date" : "AI estimate", icon: Sparkles, done: status.has_estimate && status.estimate_current, href: `/valuations?property=${propertyId}`, cta: status.has_estimate ? "Refresh the estimate" : "Get an AI estimate" },
    { label: "Digital twin", icon: Boxes, done: status.has_twin, href: `/properties/${propertyId}/twin`, cta: "Create a digital twin" },
    { label: status.verification_status === "pending" ? "Awaiting verifier" : "Verified", icon: ClipboardCheck, done: verified, href: "#verification", cta: "Upload documents and request verification", waiting: status.verification_status === "pending" },
    { label: "On the blockchain", icon: Blocks, done: status.on_chain, href: `/properties/${propertyId}/blockchain`, cta: "Commit this record" },
  ];
  const next = steps.find((step) => !step.done && !step.waiting);
  return (
    <section aria-label="Property progress" className="rounded-xl border border-slate-200 bg-white p-5 shadow-card print:hidden">
      <ol className="grid grid-cols-2 gap-3 sm:grid-cols-5">
        {steps.map(({ label, icon: Icon, done, waiting }) => (
          <li key={label} className="flex items-center gap-2 text-sm">
            <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${done ? "bg-teal-700 text-white" : waiting ? "bg-amber-100 text-amber-900" : "bg-slate-100 text-slate-500"}`}>
              {done ? <CheckCircle2 role="img" aria-label="Done" className="h-4 w-4" /> : <Icon role="img" aria-label={waiting ? "Waiting" : "Not done yet"} className="h-4 w-4" />}
            </span>
            <span className={done ? "font-medium text-navy-900" : "text-slate-600"}>{label}</span>
          </li>
        ))}
      </ol>
      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-3">
        {next ? (
          next.href.startsWith("#") ? (
            <a href={next.href} className="inline-flex items-center gap-1.5 text-sm font-medium text-teal-700">
              Next: {next.cta} <ArrowRight aria-hidden className="h-4 w-4" />
            </a>
          ) : (
            <Link to={next.href} className="inline-flex items-center gap-1.5 text-sm font-medium text-teal-700">
              Next: {next.cta} <ArrowRight aria-hidden className="h-4 w-4" />
            </Link>
          )
        ) : (
          <p className="text-sm font-medium text-teal-700">Every step is complete for this property.</p>
        )}
        {completeness && completeness.percent < 100 && (
          <p className="text-xs text-slate-600">
            Record {completeness.percent}% complete. <Link to={`/properties/${propertyId}/edit`} className="underline">Still missing</Link>: {completeness.missing.slice(0, 4).join(", ").toLowerCase()}
            {completeness.missing.length > 4 ? `, and ${completeness.missing.length - 4} more` : ""}.
          </p>
        )}
      </div>
    </section>
  );
}
