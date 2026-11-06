import { ArrowLeft, Printer } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { PricePositionBadge, RangeBar } from "../components/insights";
import { Button, Card, ClaimBadge, KeyValues, Loadable, Notice, StatusBadge, SyntheticBadge } from "../components/ui";
import { useAsync } from "../hooks/useAsync";
import { api } from "../services/api";
import { area, date, displayTitle, money, percent, plainPercent, titleCase } from "../utils/format";

/** A one-page summary to print or save as a PDF. It uses only what this viewer is allowed to see. */
export default function PropertyReportPage() {
  const { id } = useParams();
  const state = useAsync(() => Promise.all([api.properties.get(id), api.properties.insights(id)]), [id]);
  return (
    <Loadable state={state} label="Preparing the report">
      {([property, insights]) => {
        const { estimate, market, status, currency } = insights;
        return (
          <article className="mx-auto max-w-3xl space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-2 print:hidden">
              <Link to={`/properties/${id}`} className="inline-flex items-center gap-1.5 text-sm font-medium text-teal-700">
                <ArrowLeft aria-hidden className="h-4 w-4" /> Back to the property
              </Link>
              <Button onClick={() => window.print()}>
                <Printer aria-hidden className="h-4 w-4" /> Print or save as PDF
              </Button>
            </div>
            <header className="border-b-2 border-navy-900 pb-3">
              <p className="text-xs font-semibold uppercase tracking-widest text-brass-600">PropTwin AI property report</p>
              <h1 className="mt-1 text-3xl text-navy-900">{displayTitle(property)}</h1>
              <p className="mt-1 text-sm text-slate-600">
                {[property.locality, property.city, property.state].filter(Boolean).join(", ")} · Prepared {date(new Date())}
              </p>
              {property.is_demo && <div className="mt-2"><SyntheticBadge /></div>}
            </header>
            {property.is_demo && <Notice tone="warning">This is a fictional demo record. It does not describe a real property.</Notice>}
            <Card title="Value and price" action={<ClaimBadge kind="ai" />}>
              {estimate ? (
                <>
                  <p className="text-sm text-slate-600">Estimated market value</p>
                  <p className="figure text-4xl text-navy-900">{money(estimate.value, currency)}</p>
                  <RangeBar lower={estimate.lower} value={estimate.value} upper={estimate.upper} asking={insights.asking_price} currency={currency} />
                  <div className="mt-3 flex flex-wrap items-center gap-2 text-sm text-slate-700">
                    <PricePositionBadge position={insights.price_position} />
                    {insights.asking_vs_estimate_pct !== null && <span>Asking {money(insights.asking_price, currency)}, {percent(insights.asking_vs_estimate_pct, 1)} against the estimate.</span>}
                  </div>
                  <p className="mt-2 text-xs text-slate-500">
                    Model {estimate.model_version}, {date(estimate.predicted_at)}.{estimate.trained_on_synthetic_data ? " Trained on synthetic demo data." : ""}{estimate.is_current ? "" : " Out of date: the details it used have since changed."}
                  </p>
                </>
              ) : (
                <p className="text-sm text-slate-600">No AI estimate exists for this property. Asking price: {money(insights.asking_price, currency)}.</p>
              )}
            </Card>
            <Card title="Characteristics">
              <KeyValues
                items={[
                  ["Type", titleCase(property.property_type)],
                  ["Built-up area", area(property.built_up_area_sqft)],
                  ["Bedrooms and bathrooms", `${property.bedrooms ?? "Not recorded"} and ${property.bathrooms ?? "not recorded"}`],
                  ["Construction year", property.construction_year],
                  ["Condition", titleCase(property.condition)],
                  ["Amenities", property.amenities.length ? property.amenities.map(titleCase).join(", ") : "None recorded"],
                ]}
              />
            </Card>
            <Card title="Comparisons">
              <KeyValues
                items={[
                  ["Asking price per sq ft", insights.asking_per_sqft ? money(insights.asking_per_sqft, currency) : null],
                  ["Locality median per sq ft", insights.market_per_sqft ? money(insights.market_per_sqft, currency) : null],
                  ["Gross rental yield", insights.gross_yield_pct ? plainPercent(insights.gross_yield_pct) : null],
                  ["Locality gross yield", insights.market_yield_pct ? plainPercent(insights.market_yield_pct) : null],
                  ["Locality, 12-month change", market?.change_12m_pct ? percent(market.change_12m_pct, 1) : null],
                  ["Market data", market ? `${market.locality}, to ${date(market.latest_period)}${market.is_synthetic ? " (synthetic)" : ""}` : null],
                ]}
              />
            </Card>
            <Card title="Trust status">
              <ul className="space-y-2 text-sm text-slate-700">
                <li className="flex flex-wrap items-center gap-2">
                  {["verified", "rejected"].includes(status.verification_status) ? <ClaimBadge kind="document" /> : <span className="font-medium text-navy-900">Verifier review:</span>} <StatusBadge status={status.verification_status} />
                </li>
                <li className="flex flex-wrap items-center gap-2">
                  {status.on_chain ? <><ClaimBadge kind="chain" /> A hash of this record is on the blockchain.</> : <><span className="font-medium text-navy-900">Blockchain:</span> This record has not been committed.</>}
                </li>
              </ul>
            </Card>
            <Card title="What stands out">
              <ul className="list-inside list-disc space-y-1 text-sm text-slate-700">
                {insights.takeaways.map((note) => <li key={note.text}>{note.text}</li>)}
              </ul>
            </Card>
            <footer className="text-xs text-slate-500">
              {insights.disclaimer} An AI estimate is not a sale price or a certified appraisal. A verifier's decision is not a legal title search, and a blockchain record does not establish legal ownership.
            </footer>
          </article>
        );
      }}
    </Loadable>
  );
}
