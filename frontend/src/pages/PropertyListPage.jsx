import { useState } from "react";
import { useForm } from "react-hook-form";
import { ChevronDown, SlidersHorizontal, X } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import { PROPERTY_TYPES, PropertyCard } from "../components/property";
import { Button, Card, DataTable, Empty, ErrorNote, Loadable, PageHeader, Pagination, SelectField, Spinner, StatusBadge, TextField } from "../components/ui";
import { useAsync } from "../hooks/useAsync";
import { useAuth } from "../hooks/useAuth";
import { api } from "../services/api";
import { area, displayTitle, money, plainPercent, titleCase } from "../utils/format";

const SORTS = [
  { value: "newest", label: "Newest" },
  { value: "price_asc", label: "Price: low to high" },
  { value: "price_desc", label: "Price: high to low" },
  { value: "area_asc", label: "Size: small to large" },
  { value: "area_desc", label: "Size: large to small" },
];
const FILTERS = ["q", "property_type", "min_price", "max_price", "min_area", "max_area", "min_bedrooms", "verified_only", "sort"];
const ADVANCED = ["min_price", "max_price", "min_area", "max_area", "min_bedrooms"];

const perSqft = (p) => (p.asking_price && p.built_up_area_sqft ? Number(p.asking_price) / Number(p.built_up_area_sqft) : null);
const grossYield = (p) => (p.monthly_rent && p.asking_price ? (Number(p.monthly_rent) * 1200) / Number(p.asking_price) : null);

/** Marks the best figure in a row. It is only a highlight within this comparison, and the word beside it says why. */
function bestOf(properties, measure, direction) {
  const values = properties.map(measure).filter((value) => value !== null);
  if (values.length < 2 || new Set(values).size < 2) return null;
  return direction > 0 ? Math.max(...values) : Math.min(...values);
}

function CompareTable({ ids, onClose }) {
  const state = useAsync(() => api.properties.compare(ids), [ids.join(",")]);
  const rows = [
    ["Type", (p) => titleCase(p.property_type)],
    ["Location", (p) => [p.locality, p.city].filter(Boolean).join(", ")],
    ["Asking price", (p) => money(p.asking_price, p.currency)],
    ["Price per sq ft", (p) => (perSqft(p) === null ? "Not available" : money(perSqft(p), p.currency)), perSqft, -1, "lowest"],
    ["Built-up area", (p) => area(p.built_up_area_sqft)],
    ["Bedrooms", (p) => p.bedrooms ?? "Not available"],
    ["Age", (p) => (p.property_age === null ? "Not available" : `${p.property_age} years`)],
    ["Condition", (p) => titleCase(p.condition)],
    ["Monthly rent", (p) => money(p.monthly_rent, p.currency)],
    ["Gross yield", (p) => (grossYield(p) === null ? "Not available" : plainPercent(grossYield(p))), grossYield, 1, "highest"],
    ["Verification", (p) => <StatusBadge status={p.verification_status} />],
  ];
  return (
    <Card title="Compare properties" action={<Button variant="ghost" onClick={onClose}>Close</Button>} className="mb-6">
      <Loadable state={state} label="Loading comparison">
        {(properties) => (
          <>
            <DataTable
              rows={rows}
              rowKey={(row) => row[0]}
              columns={[
                { header: "Attribute", cell: (row) => <span className="font-medium">{row[0]}</span> },
                ...properties.map((property) => ({
                  header: displayTitle(property),
                  cell: ([, render, measure, direction, word]) => {
                    const top = measure ? bestOf(properties, measure, direction) : null;
                    const isTop = top !== null && measure(property) === top;
                    return (
                      <span className={isTop ? "tabular font-semibold text-teal-700" : "tabular"}>
                        {render(property)}
                        {isTop && <span className="ml-1.5 text-xs font-medium">({word})</span>}
                      </span>
                    );
                  },
                })),
              ]}
            />
            <p className="mt-3 text-xs text-slate-500">Highlights mark the figure at the end of the range in this comparison only. They are not a recommendation.</p>
          </>
        )}
      </Loadable>
    </Card>
  );
}

export default function PropertyListPage() {
  const [params, setParams] = useSearchParams();
  const { user, hasRole } = useAuth();
  const [selected, setSelected] = useState([]);
  const [comparing, setComparing] = useState(false);
  const page = Number(params.get("page") ?? 1);
  const query = Object.fromEntries(FILTERS.filter((key) => params.get(key)).map((key) => [key, params.get(key)]));

  const results = useAsync(() => api.properties.search({ ...query, page, page_size: 12 }), [params.toString()]);
  const favorites = useAsync(() => (user ? api.favorites.list() : Promise.resolve([])), [user?.id]);
  const savedIds = new Set((favorites.data ?? []).map((item) => item.id));
  const [favoriteError, setFavoriteError] = useState(null);

  const { register, handleSubmit, reset } = useForm({ defaultValues: { sort: "newest", property_type: "", ...query, verified_only: query.verified_only === "true" } });
  const [advanced, setAdvanced] = useState(() => ADVANCED.some((key) => params.get(key)));

  const applyFilters = (values) => {
    const next = new URLSearchParams();
    Object.entries(values).forEach(([key, value]) => value && next.set(key, value === true ? "true" : value));
    setParams(next);
  };

  const toggleSaved = async (id) => {
    setFavoriteError(null);
    try {
      await (savedIds.has(id) ? api.favorites.remove(id) : api.favorites.add(id));
      favorites.reload();
    } catch (error) {
      setFavoriteError(error);
    }
  };

  const toggleSelected = (id) => {
    setComparing(false);
    setSelected((current) => (current.includes(id) ? current.filter((item) => item !== id) : current.length < 4 ? [...current, id] : current));
  };

  return (
    <>
      <PageHeader
        title="Properties"
        subtitle="Public listings. Street addresses and owner details are visible only to the people entitled to them."
        action={
          hasRole("owner", "admin") && (
            <Link to="/properties/new" className="rounded-lg bg-teal-700 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-teal-600">
              Register a property
            </Link>
          )
        }
      />
      <Card className="mb-6">
        <form onSubmit={handleSubmit(applyFilters)} className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <TextField label="Search" placeholder="Title, locality or city" registration={register("q")} />
            <SelectField label="Property type" registration={register("property_type")} options={[{ value: "", label: "Any type" }, ...PROPERTY_TYPES]} />
            <SelectField label="Sort by" registration={register("sort")} options={SORTS} />
            <div className="flex items-end gap-2">
              <Button type="submit" className="flex-1">Apply</Button>
              <Button
                variant="secondary"
                onClick={() => {
                  reset({ q: "", property_type: "", min_price: "", max_price: "", min_area: "", max_area: "", min_bedrooms: "", verified_only: false, sort: "newest" });
                  setParams(new URLSearchParams());
                }}
              >
                Clear
              </Button>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-sm">
            <button type="button" aria-expanded={advanced} onClick={() => setAdvanced((value) => !value)} className="inline-flex items-center gap-1.5 font-medium text-navy-800">
              <SlidersHorizontal aria-hidden className="h-4 w-4" /> More filters <ChevronDown aria-hidden className={`h-3.5 w-3.5 transition-transform ${advanced ? "rotate-180" : ""}`} />
            </button>
            <label className="flex cursor-pointer items-center gap-2 text-slate-700">
              <input type="checkbox" className="accent-teal-700" {...register("verified_only")} /> Verified only
            </label>
          </div>
          <div hidden={!advanced} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            <TextField label="Min price" type="number" min="0" registration={register("min_price")} />
            <TextField label="Max price" type="number" min="0" registration={register("max_price")} />
            <TextField label="Min size (sq ft)" type="number" min="0" registration={register("min_area")} />
            <TextField label="Max size (sq ft)" type="number" min="0" registration={register("max_area")} />
            <TextField label="Min bedrooms" type="number" min="0" registration={register("min_bedrooms")} />
          </div>
        </form>
      </Card>

      {results.data && <p className="mb-3 text-sm text-slate-600" aria-live="polite">{results.data.total} {results.data.total === 1 ? "listing" : "listings"}{user ? "" : ". Sign in to save listings."}</p>}
      {selected.length > 0 && !comparing && (
        <div className="fixed inset-x-4 bottom-4 z-30 mx-auto flex max-w-lg items-center justify-between gap-3 rounded-xl bg-navy-900 px-4 py-3 text-sm text-white shadow-lift">
          <span>{selected.length === 1 ? "Select at least one more to compare" : `${selected.length} selected, up to 4`}</span>
          <span className="flex items-center gap-2">
            <button type="button" aria-label="Clear the comparison" onClick={() => setSelected([])} className="text-slate-300 hover:text-white">
              <X aria-hidden className="h-4 w-4" />
            </button>
            <Button disabled={selected.length < 2} onClick={() => { setComparing(true); window.scrollTo?.(0, 0); }}>Compare {selected.length} properties</Button>
          </span>
        </div>
      )}
      {comparing && <CompareTable ids={selected} onClose={() => setComparing(false)} />}
      <ErrorNote error={favoriteError} />

      {results.loading && !results.data ? (
        <Spinner label="Searching" />
      ) : results.error ? (
        <ErrorNote error={results.error} onRetry={results.reload} />
      ) : results.data.items.length === 0 ? (
        <Empty title="No properties match">Try widening your filters.</Empty>
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {results.data.items.map((property) => (
              <PropertyCard
                key={property.id}
                property={property}
                saved={savedIds.has(property.id)}
                onToggleSaved={user ? toggleSaved : undefined}
                selected={selected.includes(property.id)}
                onToggleSelected={toggleSelected}
              />
            ))}
          </div>
          <Pagination
            page={results.data.page}
            pageSize={results.data.page_size}
            total={results.data.total}
            onChange={(next) => {
              const updated = new URLSearchParams(params);
              updated.set("page", String(next));
              setParams(updated);
            }}
          />
        </>
      )}
    </>
  );
}
