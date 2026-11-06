import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { TrendChart } from "../components/charts";
import { InfoTip, PageGuide } from "../components/guide";
import { Card, ClaimBadge, ErrorNote, Notice, PageHeader, Stat } from "../components/ui";
import { useAsync } from "../hooks/useAsync";
import { api } from "../services/api";
import { displayTitle, money, plainPercent } from "../utils/format";
import { analyzeInvestment } from "../utils/finance";

// Starting points only, shown in editable fields. None of them is a quoted rate or a market claim.
const DEFAULTS = { price: 8500000, downPaymentPct: 20, closingCostPct: 6, interestRatePct: 8.5, loanYears: 20, monthlyRent: 30000, vacancyPct: 5, annualCosts: 40000, appreciationPct: 5, holdYears: 10 };

const FIELDS = [
  { group: "Purchase", items: [
    { key: "price", label: "Purchase price", step: 50000, min: 1 },
    { key: "downPaymentPct", label: "Down payment (%)", step: 1, min: 0, max: 100 },
    { key: "closingCostPct", label: "Purchase costs (%)", step: 0.5, min: 0, max: 30, hint: "Stamp duty, registration and fees. Enter what applies to you." },
  ]},
  { group: "Loan", items: [
    { key: "interestRatePct", label: "Interest rate (% a year)", step: 0.05, min: 0, max: 40, hint: "Use the rate your lender quotes." },
    { key: "loanYears", label: "Loan term (years)", step: 1, min: 1, max: 40 },
  ]},
  { group: "Income and costs", items: [
    { key: "monthlyRent", label: "Monthly rent", step: 500, min: 0 },
    { key: "vacancyPct", label: "Vacancy (% of the year)", step: 1, min: 0, max: 100 },
    { key: "annualCosts", label: "Yearly costs", step: 1000, min: 0, hint: "Maintenance, society fees, insurance and property tax." },
  ]},
  { group: "Projection", items: [
    { key: "appreciationPct", label: "Yearly value change (%)", step: 0.5, min: -20, max: 30, hint: "Your assumption, not a forecast. Try a low or negative figure too." },
    { key: "holdYears", label: "Years to project", step: 1, min: 1, max: 40 },
  ]},
];

export default function CalculatorPage() {
  const [params] = useSearchParams();
  const propertyId = params.get("property");
  const property = useAsync(() => (propertyId ? api.properties.get(propertyId) : Promise.resolve(null)), [propertyId]);
  const [raw, setRaw] = useState(() => Object.fromEntries(Object.entries(DEFAULTS).map(([key, value]) => [key, String(value)])));

  useEffect(() => {
    if (!property.data) return;
    setRaw((current) => ({
      ...current,
      ...(property.data.asking_price ? { price: String(Number(property.data.asking_price)) } : {}),
      ...(property.data.monthly_rent ? { monthlyRent: String(Number(property.data.monthly_rent)) } : {}),
    }));
  }, [property.data]);

  const currency = property.data?.currency ?? "INR";
  const values = Object.fromEntries(Object.entries(raw).map(([key, value]) => [key, Number(value)]));
  const invalid = FIELDS.flatMap((group) => group.items).filter(({ key, min, max }) => raw[key] === "" || !Number.isFinite(values[key]) || (min !== undefined && values[key] < min) || (max !== undefined && values[key] > max));
  const result = useMemo(() => (invalid.length ? null : analyzeInvestment(values)), [raw]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <>
      <PageHeader title="Investment calculator" subtitle="Work out instalments, cash flow and returns from your own assumptions. Results update as you type." action={<ClaimBadge kind="hypothetical" />} />
      <PageGuide id="calculator" steps={["Start from a property's Calculate returns link, or enter your own figures.", "Replace the example rate, costs and growth with figures that apply to you.", "Look at monthly cash flow and break-even rent first. Then try a pessimistic version."]} />
      <ErrorNote error={property.error} />
      {property.data && (
        <div className="mb-4">
          <Notice>
            Using the asking price and rent from <Link className="font-medium underline" to={`/properties/${property.data.id}`}>{displayTitle(property.data)}</Link>. The other figures are examples for you to replace.
          </Notice>
        </div>
      )}
      <div className="grid items-start gap-5 lg:grid-cols-[22rem_1fr]">
        <Card>
          <form className="space-y-5" onSubmit={(event) => event.preventDefault()}>
            {FIELDS.map(({ group, items }) => (
              <fieldset key={group} className="space-y-3">
                <legend className="text-sm font-semibold text-navy-900">{group}</legend>
                {items.map(({ key, label, step, min, max, hint }) => (
                  <label key={key} className="block text-sm font-medium text-navy-800">
                    {label}
                    <input
                      type="number"
                      inputMode="decimal"
                      value={raw[key]}
                      step={step}
                      min={min}
                      max={max}
                      aria-invalid={invalid.some((item) => item.key === key)}
                      onChange={(event) => setRaw((current) => ({ ...current, [key]: event.target.value }))}
                      className="tabular mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-normal aria-[invalid=true]:border-red-500"
                    />
                    {hint && <span className="mt-1 block text-xs font-normal text-slate-500">{hint}</span>}
                  </label>
                ))}
              </fieldset>
            ))}
          </form>
        </Card>
        <div className="space-y-4">
          {!result ? (
            <ErrorNote error={`Check these figures: ${invalid.map((item) => item.label).join(", ")}.`} />
          ) : (
            <>
              <div className="grid gap-3 sm:grid-cols-3">
                <Stat label="Monthly instalment" value={money(result.instalment, currency)} hint={`${money(result.loan, currency)} borrowed`} />
                <Stat label="Monthly cash flow" value={money(result.monthlyCashFlow, currency)} hint={result.monthlyCashFlow < 0 ? "Rent does not cover the instalment and costs" : "After instalment and costs"} />
                <Stat label="Break-even rent" value={result.breakEvenRent === null ? "Not available" : money(result.breakEvenRent, currency)} hint="A month, to cover instalment and costs" />
              </div>
              <Card title="Returns">
                <dl className="grid gap-x-6 gap-y-4 sm:grid-cols-2 lg:grid-cols-3">
                  {[
                    ["Gross yield", plainPercent(result.grossYieldPct), "A year's rent as a percentage of the price, before any costs."],
                    ["Cap rate", plainPercent(result.capRatePct), "Rent after vacancy and costs, as a percentage of the price. It ignores the loan, so you can compare properties fairly."],
                    ["Cash-on-cash return", plainPercent(result.cashOnCashPct), "A year's cash flow after the loan, as a percentage of the cash you put in."],
                    ["Debt coverage", result.debtCoverage === null ? "No loan" : `${result.debtCoverage.toFixed(2)}x`, "Net income divided by loan payments. Below 1.00x, rent does not cover the loan."],
                    ["Cash needed upfront", money(result.cashInvested, currency), "Down payment plus purchase costs."],
                    ["Total interest over the loan", money(result.totalInterest, currency), "What the loan costs if it runs its full term."],
                  ].map(([label, value, tip]) => (
                    <div key={label}>
                      <dt className="flex items-center gap-1.5 text-xs font-medium text-slate-600">{label} <InfoTip label={label}>{tip}</InfoTip></dt>
                      <dd className="tabular mt-0.5 text-lg font-semibold text-navy-900">{value}</dd>
                    </div>
                  ))}
                </dl>
              </Card>
              <Card title="Projected equity" action={<ClaimBadge kind="hypothetical" />}>
                <TrendChart
                  label="Projected equity by year, from your assumptions"
                  points={result.projection.map((row) => ({ x: row.year, value: row.equity.toFixed(0) }))}
                  currency={currency}
                  xFormat={(year) => `Year ${year}`}
                  xHeader="Year"
                  valueHeader="Equity"
                  height={240}
                />
                <p className="mt-2 text-xs text-slate-500">Equity is the assumed property value minus the remaining loan. It applies the same yearly change every year, which real prices never do.</p>
              </Card>
              <Notice tone="warning">
                This is a hypothetical calculation from the figures on the left, not a forecast or financial advice. It leaves out income tax, rent growth, major repairs and the cost of selling.
              </Notice>
            </>
          )}
        </div>
      </div>
    </>
  );
}
