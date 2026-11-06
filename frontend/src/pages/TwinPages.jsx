import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { z } from "zod";
import { ComparisonBars, TrendChart } from "../components/charts";
import { PageGuide } from "../components/guide";
import { CONDITIONS } from "../components/property";
import { Button, Card, ClaimBadge, DataTable, Empty, ErrorNote, KeyValues, Loadable, Notice, PageHeader, SelectField, Stat, SuccessNote, TextField } from "../components/ui";
import { useAction, useAsync } from "../hooks/useAsync";
import { useAuth } from "../hooks/useAuth";
import { api } from "../services/api";
import { dateTime, money, percent, plainPercent, titleCase } from "../utils/format";

const pct = (min, max) => z.coerce.number({ invalid_type_error: "Enter a number." }).min(min, `Must be at least ${min}.`).max(max, `Must be at most ${max}.`);
const optionalMoney = z.preprocess((value) => (value === "" || value === undefined ? undefined : value), z.coerce.number().min(0, "Cannot be negative.").optional());

export const scenarioSchema = z
  .object({
    name: z.string().trim().min(1, "Name this scenario.").max(120),
    market_change_pct: pct(-90, 200),
    renovation_value_uplift_pct: pct(0, 100),
    condition_after: z.preprocess((value) => value || undefined, z.string().optional()),
    monthly_rent_change_pct: pct(-100, 200),
    annual_maintenance_cost: optionalMoney,
    maintenance_change_pct: pct(-100, 500),
    renovation_cost: optionalMoney,
  })
  .refine((values) => !values.condition_after || Number(values.renovation_value_uplift_pct) === 0, {
    path: ["renovation_value_uplift_pct"],
    message: "Use either a new condition or an uplift, not both: together they would count the renovation twice.",
  });

const PRESETS = [
  { label: "Market +5%", values: { name: "Market up 5%", market_change_pct: 5 } },
  { label: "Market -10%", values: { name: "Market down 10%", market_change_pct: -10 } },
  { label: "Renovation +8%", values: { name: "Renovation adds 8%", renovation_value_uplift_pct: 8 } },
  { label: "Rent +10%", values: { name: "Rent up 10%", monthly_rent_change_pct: 10 } },
  { label: "Maintenance +25%", values: { name: "Maintenance up 25%", maintenance_change_pct: 25 } },
];
const DEFAULTS = { name: "", market_change_pct: 0, renovation_value_uplift_pct: 0, condition_after: "", monthly_rent_change_pct: 0, annual_maintenance_cost: "", maintenance_change_pct: 0, renovation_cost: "" };

function toRequest(values) {
  const body = { name: values.name };
  for (const key of ["market_change_pct", "renovation_value_uplift_pct", "monthly_rent_change_pct", "maintenance_change_pct"]) body[key] = String(values[key]);
  if (values.condition_after) body.condition_after = values.condition_after;
  if (values.annual_maintenance_cost !== undefined) body.annual_maintenance_cost = Number(values.annual_maintenance_cost).toFixed(2);
  if (values.renovation_cost !== undefined) body.renovation_cost = Number(values.renovation_cost).toFixed(2);
  return body;
}

export function ScenarioForm({ twinId, onResult }) {
  const [error, setError] = useState(null);
  const { register, handleSubmit, reset, formState } = useForm({ resolver: zodResolver(scenarioSchema), defaultValues: DEFAULTS });
  const errors = formState.errors;
  const onSubmit = async (values) => {
    setError(null);
    try {
      onResult(await api.twins.simulate(twinId, toRequest(values)));
    } catch (caught) {
      setError(caught);
    }
  };
  return (
    <form onSubmit={handleSubmit(onSubmit)} noValidate className="space-y-3">
      <ErrorNote error={error} />
      <div className="flex flex-wrap gap-1.5">
        {PRESETS.map((preset) => (
          <button key={preset.label} type="button" className="rounded-full border border-slate-300 px-2.5 py-1 text-xs font-medium text-navy-800 hover:bg-slate-50" onClick={() => reset({ ...DEFAULTS, ...preset.values })}>
            {preset.label}
          </button>
        ))}
      </div>
      <TextField label="Scenario name" registration={register("name")} error={errors.name?.message} />
      <TextField label="Local market change (%)" type="number" step="0.1" registration={register("market_change_pct")} error={errors.market_change_pct?.message} />
      <TextField label="Renovation value uplift (%)" type="number" step="0.1" registration={register("renovation_value_uplift_pct")} error={errors.renovation_value_uplift_pct?.message} />
      <SelectField
        label="Condition after renovation"
        registration={register("condition_after")}
        hint="Choosing one reruns the valuation model with this condition."
        options={[{ value: "", label: "No change" }, ...CONDITIONS]}
      />
      <TextField label="Renovation cost" type="number" registration={register("renovation_cost")} error={errors.renovation_cost?.message} hint="Recorded as an assumption, not subtracted from value." />
      <TextField label="Rental income change (%)" type="number" step="0.1" registration={register("monthly_rent_change_pct")} error={errors.monthly_rent_change_pct?.message} />
      <TextField label="Annual maintenance cost" type="number" registration={register("annual_maintenance_cost")} error={errors.annual_maintenance_cost?.message} hint="Blank uses the twin's recorded cost." />
      <TextField label="Maintenance cost change (%)" type="number" step="0.1" registration={register("maintenance_change_pct")} error={errors.maintenance_change_pct?.message} />
      <Button type="submit" busy={formState.isSubmitting} className="w-full" disabled={!twinId}>
        Run scenario
      </Button>
    </form>
  );
}

export function SimulationResult({ run, currency = "INR" }) {
  return (
    <Card title={run.name} action={<ClaimBadge kind="hypothetical" />}>
      <div className="grid gap-3 sm:grid-cols-3">
        <Stat label="Baseline estimate" value={money(run.baseline_value, currency)} />
        <Stat label="Scenario value" value={money(run.scenario_value, currency)} />
        <Stat label="Difference" value={percent(run.percentage_difference)} hint={money(run.absolute_difference, currency)} />
      </div>
      <div className="mt-4">
        <ComparisonBars baseline={run.baseline_value} scenario={run.scenario_value} currency={currency} label={`Baseline against scenario for ${run.name}`} />
      </div>
      <div className="mt-4">
        <KeyValues
          items={[
            ["Annual rental income", run.annual_rental_income ? money(run.annual_rental_income, currency) : "Not calculated"],
            ["Estimated rental yield", run.rental_yield_pct ? plainPercent(run.rental_yield_pct) : "Not calculated"],
            ["Annual maintenance cost", run.annual_maintenance_cost ? money(run.annual_maintenance_cost, currency) : "Not calculated"],
            ["Simulated", dateTime(run.created_at)],
          ]}
        />
      </div>
      <div className="mt-4 rounded-md bg-slate-50 p-3 text-sm">
        <p className="font-medium text-navy-900">{run.method === "model_rerun" ? "How this was calculated: the model was rerun" : "How this was calculated: a formula"}</p>
        <p className="mt-1 text-slate-700">{run.calculation_note}</p>
        {run.assumptions.length > 0 && (
          <ul className="mt-2 flex flex-wrap gap-1.5">
            {run.assumptions.filter((item) => Number(item.value) !== 0).map((item) => (
              <li key={item.name} className="rounded-full bg-white px-2 py-0.5 text-xs text-slate-700">
                {titleCase(item.name)}: {item.value}
                {item.unit === "percent" ? "%" : ""}
              </li>
            ))}
          </ul>
        )}
      </div>
      <div className="mt-3">
        <Notice tone="warning">
          <ul className="list-inside list-disc space-y-1">
            {run.limitations.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        </Notice>
      </div>
    </Card>
  );
}

function OperatingForm({ twin, onSaved }) {
  const { register, handleSubmit, formState } = useForm({
    defaultValues: { annual_maintenance_cost: twin.annual_maintenance_cost ?? "", maintenance_notes: twin.state.operating?.maintenance_notes ?? "" },
  });
  const save = useAction(async (values) => {
    onSaved(await api.twins.update(twin.id, { annual_maintenance_cost: values.annual_maintenance_cost === "" ? null : Number(values.annual_maintenance_cost).toFixed(2), maintenance_notes: values.maintenance_notes || null }));
  });
  return (
    <form onSubmit={handleSubmit((values) => save.run(values))} className="space-y-3">
      <ErrorNote error={save.error} />
      <TextField label="Annual maintenance cost" type="number" min="0" registration={register("annual_maintenance_cost")} />
      <TextField label="Maintenance notes" registration={register("maintenance_notes")} />
      <Button type="submit" variant="secondary" busy={save.busy || formState.isSubmitting}>
        Save and record a snapshot
      </Button>
    </form>
  );
}

export function TwinWorkspacePage() {
  const { id } = useParams();
  const { user } = useAuth();
  const property = useAsync(() => api.properties.get(id), [id]);
  const twinState = useAsync(() => api.twins.forProperty(id).catch((error) => (error.status === 404 ? null : Promise.reject(error))), [id]);
  const twin = twinState.data;
  const canManage = property.data?.owner_id === user?.id || user?.roles.includes("admin");
  const history = useAsync(() => (twin && canManage ? api.twins.history(twin.id, { page_size: 50 }) : Promise.resolve({ items: [] })), [twin?.id, twin?.version, canManage]);
  const simulations = useAsync(() => (twin ? api.twins.simulations(twin.id, { page_size: 20 }) : Promise.resolve({ items: [] })), [twin?.id]);
  const market = useAsync(() => (twin ? api.twins.market(twin.id) : Promise.resolve([])), [twin?.id]);
  const [latestRun, setLatestRun] = useState(null);
  const create = useAction(async () => {
    await api.twins.create(id);
    await twinState.reload();
  });
  const currency = property.data?.currency ?? "INR";

  if (property.loading || (twinState.loading && !twin)) return <Loadable state={property} label="Loading twin">{() => null}</Loadable>;
  if (property.error) return <ErrorNote error={property.error} onRetry={property.reload} />;
  if (twinState.error) return <ErrorNote error={twinState.error} onRetry={twinState.reload} />;

  if (!twin) {
    return (
      <>
        <PageHeader title="Digital twin" subtitle={property.data.title} />
        <Empty
          title="This property has no digital twin yet"
          action={
            canManage ? (
              <>
                <Button busy={create.busy} onClick={() => create.run()}>
                  Create digital twin
                </Button>
                <div className="mt-3">
                  <ErrorNote error={create.error} />
                </div>
              </>
            ) : undefined
          }
        >
          A twin is a software copy of this record that keeps every past state and lets you test scenarios. Creating it also requests a valuation if a model is active.
        </Empty>
      </>
    );
  }

  const state = twin.state;
  const snapshots = history.data?.items ?? [];
  return (
    <>
      <PageHeader title="Digital twin workspace" subtitle={<Link className="text-teal-700 underline" to={`/properties/${id}`}>{property.data.title}</Link>} />
      <PageGuide
        id="twin"
        steps={["Check the current state and estimate. The twin follows the property record and keeps every past version.", "Pick a preset or enter your own assumptions, then run a scenario.", "Read the result and how it was calculated. Scenarios are saved below, so you can return to them."]}
      />
      <div className="mb-4">
        <Notice>{twin.twin_type} Scenarios here never change the real property record.</Notice>
      </div>
      <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Current estimate" value={twin.current_estimated_value ? money(twin.current_estimated_value, currency) : "None yet"} hint={twin.valuation_is_stale ? "Out of date: the property changed since this estimate" : `As of ${dateTime(twin.last_valuation_at)}`} />
        <Stat label="Twin version" value={twin.version} hint={`Synced ${dateTime(twin.last_synced_at)}`} />
        <Stat label="Market index" value={twin.market_index ? Number(twin.market_index).toFixed(1) : "None"} hint="Locality index" />
        <Stat label="Annual maintenance" value={twin.annual_maintenance_cost ? money(twin.annual_maintenance_cost, currency) : "Not recorded"} />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4">
          <Card title="Run a scenario" action={<ClaimBadge kind="hypothetical" />}>
            {twin.current_estimated_value ? (
              <ScenarioForm
                twinId={twin.id}
                onResult={(run) => {
                  setLatestRun(run);
                  simulations.reload();
                }}
              />
            ) : (
              <Notice tone="warning">A scenario needs a baseline estimate. <Link className="underline" to={`/valuations?property=${id}`}>Request a valuation</Link> first.</Notice>
            )}
          </Card>
          {canManage && (
            <Card title="Operating information">
              <OperatingForm key={twin.version} twin={twin} onSaved={() => twinState.reload()} />
            </Card>
          )}
        </div>
        <div className="space-y-4 lg:col-span-2">
          {latestRun && <SimulationResult run={latestRun} currency={currency} />}
          <Card title="Current state">
            <KeyValues
              items={[
                ["Condition", titleCase(state.condition)],
                ["Built-up area", state.built_up_area_sqft ? `${state.built_up_area_sqft} sq ft` : null],
                ["Monthly rent", money(state.monthly_rent, currency)],
                ["Listing", titleCase(state.listing_status)],
                ["Verification", titleCase(state.verification_status)],
                ["Renovations", state.renovations.length || "None recorded"],
                ["Maintenance notes", state.operating?.maintenance_notes ?? "None"],
              ]}
            />
          </Card>
          {canManage && (
            <Card title="Estimated value across snapshots" action={<ClaimBadge kind="ai" />}>
              <TrendChart
                label="Estimated value in each twin snapshot"
                valueHeader="Estimate"
                currency={currency}
                points={[...snapshots].reverse().filter((item) => item.estimated_value).map((item) => ({ x: item.created_at, value: item.estimated_value }))}
                emptyTitle="No estimates in the twin's history yet"
              />
            </Card>
          )}
          <Card title="Locality market index" action={market.data?.some((point) => point.is_synthetic) ? <span className="text-xs font-medium text-amber-800">Synthetic, not market data</span> : null}>
            <TrendChart
              label="Locality market index over time"
              valueHeader="Index"
              points={(market.data ?? []).map((point) => ({ x: point.period, value: point.price_index }))}
              valueFormat={(value) => Number(value).toFixed(1)}
              yFormat={(value) => Number(value).toFixed(0)}
              emptyTitle="No market data for this locality"
            />
          </Card>
          {canManage && (
            <Card title="Historical snapshots">
              <DataTable
                rows={snapshots}
                rowKey={(row) => row.id}
                columns={[
                  { header: "Version", cell: (row) => row.version },
                  { header: "When", cell: (row) => dateTime(row.created_at) },
                  { header: "Reason", cell: (row) => titleCase(row.reason) },
                  { header: "Changed", cell: (row) => row.changed_fields.map(titleCase).join(", ") || "None" },
                  { header: "Estimate", cell: (row) => <span className="tabular">{money(row.estimated_value, currency)}</span> },
                ]}
              />
            </Card>
          )}
          <Card title="Simulation history" action={<ClaimBadge kind="hypothetical" />}>
            <DataTable
              rows={simulations.data?.items ?? []}
              rowKey={(row) => row.id}
              empty={<Empty title="No scenarios run yet" />}
              columns={[
                { header: "Scenario", cell: (row) => <button type="button" className="text-left font-medium text-teal-700 underline" onClick={() => setLatestRun(row)}>{row.name}</button> },
                { header: "Method", cell: (row) => (row.method === "model_rerun" ? "Model rerun" : "Formula") },
                { header: "Scenario value", cell: (row) => <span className="tabular">{money(row.scenario_value, currency)}</span> },
                { header: "Difference", cell: (row) => <span className="tabular">{percent(row.percentage_difference)}</span> },
                { header: "When", cell: (row) => dateTime(row.created_at) },
              ]}
            />
          </Card>
        </div>
      </div>
    </>
  );
}

export function SimulatorPage() {
  const { hasRole } = useAuth();
  const [params, setParams] = useSearchParams();
  const owned = useAsync(() => (hasRole("owner", "admin") ? api.properties.mine({ page_size: 100 }).then((page) => page.items) : Promise.resolve([])), []);
  const saved = useAsync(() => api.favorites.list(), []);
  const selected = params.get("property") ?? "";
  const twin = useAsync(() => (selected ? api.twins.forProperty(selected).catch((error) => (error.status === 404 ? null : Promise.reject(error))) : Promise.resolve(null)), [selected]);
  const [runs, setRuns] = useState([]);
  useEffect(() => setRuns([]), [selected]);

  const options = [...(owned.data ?? []), ...(saved.data ?? []).filter((item) => !(owned.data ?? []).some((own) => own.id === item.id))];
  const propertyLabel = options.find((item) => item.id === selected);

  return (
    <>
      <PageHeader title="Market scenario simulator" subtitle="Test what-if assumptions and compare them side by side. These are hypothetical calculations, not forecasts." />
      <PageGuide
        id="simulator"
        steps={["Choose one of your properties or saved listings. It needs a digital twin.", "Pick a preset such as Market -10%, or enter your own assumptions.", "Run several scenarios. They line up in a table, so you can compare them side by side."]}
      />
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4">
          <Card title="Property">
            <label htmlFor="simulator-property" className="text-sm font-medium text-navy-800">
              Your properties and favorites
            </label>
            <select id="simulator-property" value={selected} onChange={(event) => setParams(event.target.value ? { property: event.target.value } : {})} className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm">
              <option value="">Select a property</option>
              {options.map((property) => (
                <option key={property.id} value={property.id}>
                  {property.title}
                </option>
              ))}
            </select>
          </Card>
          {selected && (
            <Loadable state={{ ...twin, data: twin.loading ? null : { twin: twin.data } }} label="Loading twin">
              {({ twin: loaded }) =>
                loaded ? (
                  <Card title="Assumptions" action={<ClaimBadge kind="hypothetical" />}>
                    <ScenarioForm twinId={loaded.id} onResult={(run) => setRuns((current) => [run, ...current])} />
                  </Card>
                ) : (
                  <Empty title="No digital twin for this property" action={<Link className="font-medium text-teal-700" to={`/properties/${selected}/twin`}>Go to its twin</Link>}>
                    Scenarios run on a twin, which the property's owner creates.
                  </Empty>
                )
              }
            </Loadable>
          )}
        </div>
        <div className="space-y-4 lg:col-span-2">
          {runs.length > 1 && (
            <Card title="Scenarios compared">
              <DataTable
                rows={runs}
                rowKey={(row) => row.id}
                columns={[
                  { header: "Scenario", cell: (row) => row.name },
                  { header: "Baseline", cell: (row) => <span className="tabular">{money(row.baseline_value, propertyLabel?.currency)}</span> },
                  { header: "Scenario value", cell: (row) => <span className="tabular">{money(row.scenario_value, propertyLabel?.currency)}</span> },
                  { header: "Difference", cell: (row) => <span className="tabular">{percent(row.percentage_difference)}</span> },
                  { header: "Yield", cell: (row) => (row.rental_yield_pct ? plainPercent(row.rental_yield_pct) : "Not calculated") },
                ]}
              />
            </Card>
          )}
          {runs.length === 0 ? (
            <Empty title="No scenarios yet">{selected ? "Set your assumptions and run a scenario." : "Choose a property to begin. Investors can save a listing to see it here."}</Empty>
          ) : (
            <SimulationResult run={runs[0]} currency={propertyLabel?.currency} />
          )}
          {runs.length > 0 && <SuccessNote>Saved to this twin's simulation history.</SuccessNote>}
        </div>
      </div>
    </>
  );
}
