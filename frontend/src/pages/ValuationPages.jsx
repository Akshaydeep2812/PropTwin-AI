import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useSearchParams } from "react-router-dom";
import { z } from "zod";
import { TrendChart } from "../components/charts";
import { PageGuide } from "../components/guide";
import { CONDITIONS, PROPERTY_TYPES, ValuationResult } from "../components/property";
import { Button, Card, ClaimBadge, DataTable, Empty, ErrorNote, Loadable, PageHeader, SelectField, SyntheticBadge, TextField } from "../components/ui";
import { useAction, useAsync } from "../hooks/useAsync";
import { useAuth } from "../hooks/useAuth";
import { api } from "../services/api";
import { dateTime, money } from "../utils/format";

const optional = (schema) => z.preprocess((value) => (value === "" || value === undefined ? undefined : value), schema.optional());
const manualSchema = z.object({
  property_type: z.enum(["apartment", "house", "villa", "townhouse", "plot", "commercial"]),
  built_up_area_sqft: z.coerce.number({ invalid_type_error: "Enter a number." }).positive("Must be greater than zero."),
  locality: z.string().optional(),
  city: z.string().optional(),
  bedrooms: optional(z.coerce.number().int().min(0)),
  bathrooms: optional(z.coerce.number().int().min(0)),
  construction_year: optional(z.coerce.number().int().min(1800).max(2100)),
  condition: optional(z.enum(["poor", "fair", "good", "very_good", "excellent"])),
});

function useMyProperties() {
  const { hasRole } = useAuth();
  return useAsync(async () => {
    const [owned, saved] = await Promise.all([hasRole("owner", "admin") ? api.properties.mine({ page_size: 100 }).then((page) => page.items) : [], api.favorites.list().catch(() => [])]);
    return [...owned, ...saved.filter((item) => !owned.some((own) => own.id === item.id))];
  }, []);
}

const EXAMPLE = { property_type: "apartment", built_up_area_sqft: 1250, locality: "Riverside", city: "Sample City", bedrooms: 2, bathrooms: 2, construction_year: 2016, condition: "good" };

function ManualForm({ onResult }) {
  const [error, setError] = useState(null);
  const { register, handleSubmit, formState, reset, watch, setValue } = useForm({ resolver: zodResolver(manualSchema), defaultValues: { property_type: "apartment", condition: "" } });
  const errors = formState.errors;
  const market = useAsync(() => api.market.localities().catch(() => null), []);
  const localities = market.data?.localities ?? [];
  const locality = watch("locality");
  // Choosing a known locality fills in its city, which the model also uses.
  useEffect(() => {
    const match = localities.find((item) => item.locality === locality);
    if (match) setValue("city", match.city);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [locality, localities.length]);
  const onSubmit = async (values) => {
    setError(null);
    const features = Object.fromEntries(Object.entries(values).filter(([, value]) => value !== undefined && value !== ""));
    features.built_up_area_sqft = String(features.built_up_area_sqft);
    try {
      onResult(await api.valuations.predict({ features }));
    } catch (caught) {
      setError(caught);
    }
  };
  return (
    <form onSubmit={handleSubmit(onSubmit)} noValidate className="space-y-3">
      <ErrorNote error={error} />
      <button type="button" onClick={() => reset(EXAMPLE)} className="text-sm font-medium text-teal-700 underline">
        Fill in an example
      </button>
      <SelectField label="Property type" registration={register("property_type")} options={PROPERTY_TYPES} />
      <TextField label="Built-up area (sq ft)" type="number" registration={register("built_up_area_sqft")} error={errors.built_up_area_sqft?.message} />
      <TextField label="Locality" list="known-localities" registration={register("locality")} hint={localities.length ? "Pick a suggestion, or type your own." : undefined} />
      <datalist id="known-localities">
        {localities.map((item) => (
          <option key={item.locality} value={item.locality} />
        ))}
      </datalist>
      <TextField label="City" registration={register("city")} />
      <div className="grid grid-cols-2 gap-3">
        <TextField label="Bedrooms" type="number" registration={register("bedrooms")} error={errors.bedrooms?.message} />
        <TextField label="Bathrooms" type="number" registration={register("bathrooms")} error={errors.bathrooms?.message} />
      </div>
      <TextField label="Construction year" type="number" registration={register("construction_year")} error={errors.construction_year?.message} />
      <SelectField label="Condition" registration={register("condition")} options={[{ value: "", label: "Not specified" }, ...CONDITIONS]} />
      <Button type="submit" busy={formState.isSubmitting} className="w-full">
        Predict valuation
      </Button>
    </form>
  );
}

export function ValuationWorkspacePage() {
  const [params] = useSearchParams();
  const properties = useMyProperties();
  const [propertyId, setPropertyId] = useState(params.get("property") ?? "");
  const [result, setResult] = useState(null);
  const predict = useAction(async (id) => setResult(await api.valuations.predict({ property_id: id })));
  const options = properties.data ?? [];
  const external = propertyId && !options.some((item) => item.id === propertyId);

  useEffect(() => setResult(null), [propertyId]);

  return (
    <>
      <PageHeader title="AI valuation workspace" subtitle="Each result comes from the active trained model. If no approved model is active, you will see that instead of a figure." />
      <PageGuide
        id="valuation"
        steps={["Choose a registered or saved property, or enter its details by hand.", "Select Predict valuation. The figure comes with a range: the wider it is, the less certain the model is.", "Read what moved the number and its limitations before relying on it."]}
      />
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4">
          <Card title="Value a registered property">
            <label className="text-sm font-medium text-navy-800" htmlFor="property-select">
              Property
            </label>
            <select id="property-select" value={propertyId} onChange={(event) => setPropertyId(event.target.value)} className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm">
              <option value="">Select a property</option>
              {external && <option value={propertyId}>Selected listing</option>}
              {options.map((property) => (
                <option key={property.id} value={property.id}>
                  {property.title}
                </option>
              ))}
            </select>
            <Button className="mt-3 w-full" disabled={!propertyId} busy={predict.busy} onClick={() => predict.run(propertyId)}>
              Predict valuation
            </Button>
            <div className="mt-3">
              <ErrorNote error={predict.error} />
            </div>
          </Card>
          <Card title="Or enter details">
            <ManualForm onResult={setResult} />
          </Card>
        </div>
        <div className="lg:col-span-2">
          {result ? (
            <div className="space-y-4">
              <ValuationResult valuation={result} />
              {result.property_id && (
                <Card title="What to do with this estimate">
                  <ul className="grid gap-2 text-sm sm:grid-cols-3">
                    <li><Link className="font-medium text-teal-700 underline" to={`/properties/${result.property_id}`}>Check the asking price against it</Link></li>
                    <li><Link className="font-medium text-teal-700 underline" to={`/calculator?property=${result.property_id}`}>Work out the returns</Link></li>
                    <li><Link className="font-medium text-teal-700 underline" to={`/simulator?property=${result.property_id}`}>Test a what-if scenario</Link></li>
                  </ul>
                </Card>
              )}
            </div>
          ) : (
            <Empty title="No estimate yet">Choose a property or enter its details, then predict a valuation. You will see a value, a range, the factors that moved it, and its limits.</Empty>
          )}
        </div>
      </div>
    </>
  );
}

export function ValuationHistoryPage() {
  const [params, setParams] = useSearchParams();
  const properties = useMyProperties();
  const dashboard = useAsync(() => api.dashboard(), []);
  const selected = params.get("property") ?? "";
  const history = useAsync(() => (selected ? api.properties.valuations(selected, { page_size: 100 }) : Promise.resolve(null)), [selected]);
  const options = properties.data ?? [];

  return (
    <>
      <PageHeader title="Valuation history" subtitle="Every saved estimate. Earlier ones are never altered, including when a newer model replaces the old one." />
      <Card className="mb-4">
        <label htmlFor="history-property" className="text-sm font-medium text-navy-800">
          Property
        </label>
        <select
          id="history-property"
          value={selected}
          onChange={(event) => setParams(event.target.value ? { property: event.target.value } : {})}
          className="mt-1 w-full max-w-md rounded-md border border-slate-300 bg-white px-3 py-2 text-sm"
        >
          <option value="">My recent estimates</option>
          {options.map((property) => (
            <option key={property.id} value={property.id}>
              {property.title}
            </option>
          ))}
        </select>
      </Card>

      {selected ? (
        <Loadable state={history} label="Loading history">
          {(rows) => (
            <div className="space-y-4">
              <Card title="Estimated value over time" action={<ClaimBadge kind="ai" />}>
                <TrendChart
                  label="Estimated value over time"
                  valueHeader="Estimate"
                  currency={rows[0]?.currency}
                  points={[...rows].reverse().map((row) => ({ x: row.predicted_at, value: row.predicted_value }))}
                  emptyTitle="No estimates for this property"
                  emptyText="Request one from the valuation workspace."
                />
              </Card>
              <Card title="All estimates">
                <DataTable
                  rows={rows}
                  rowKey={(row) => row.id}
                  empty={<Empty title="No estimates for this property" />}
                  columns={[
                    { header: "Date", cell: (row) => dateTime(row.predicted_at) },
                    { header: "Estimate", cell: (row) => <span className="tabular font-medium">{money(row.predicted_value, row.currency)}</span> },
                    { header: "Range", cell: (row) => <span className="tabular">{money(row.interval_lower, row.currency)} to {money(row.interval_upper, row.currency)}</span> },
                    { header: "Model", cell: (row) => <span className="text-xs">{row.model_version}</span> },
                    { header: "Data", cell: (row) => (row.trained_on_synthetic_data ? <SyntheticBadge /> : "Real") },
                  ]}
                />
              </Card>
            </div>
          )}
        </Loadable>
      ) : (
        <Loadable state={dashboard} label="Loading history">
          {(data) => (
            <Card title="My recent estimates" action={<ClaimBadge kind="ai" />}>
              <DataTable
                rows={[...data.valuation_trend].reverse()}
                rowKey={(row) => row.id}
                empty={<Empty title="No estimates yet" action={<Link className="font-medium text-teal-700" to="/valuations">Open the valuation workspace</Link>} />}
                columns={[
                  { header: "Date", cell: (row) => dateTime(row.predicted_at) },
                  { header: "Property", cell: (row) => (row.property_id ? <Link className="text-teal-700 underline" to={`/properties/${row.property_id}`}>{row.property_title}</Link> : "Entered manually") },
                  { header: "Estimate", cell: (row) => <span className="tabular font-medium">{money(row.predicted_value, row.currency)}</span> },
                  { header: "Model", cell: (row) => <span className="text-xs">{row.model_version}</span> },
                ]}
              />
            </Card>
          )}
        </Loadable>
      )}
    </>
  );
}
