import { Banknote, MapPinned, Percent, TrendingUp } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { IndexComparison } from "../components/charts";
import { InfoTip, PageGuide } from "../components/guide";
import { Button, Card, DataTable, Empty, ErrorNote, Loadable, Notice, PageHeader, Spinner, Stat, SyntheticBadge } from "../components/ui";
import { useAsync } from "../hooks/useAsync";
import { api } from "../services/api";
import { date, money, percent, plainPercent } from "../utils/format";

const RANKINGS = [
  { value: "change_12m_pct", label: "12-month change" },
  { value: "cagr_5y_pct", label: "5-year growth per year" },
  { value: "gross_yield_pct", label: "Gross rental yield" },
  { value: "price_per_sqft", label: "Price per sq ft" },
];

const best = (rows, field, direction = 1) => rows.filter((row) => row[field] !== null).reduce((top, row) => (top === null || direction * Number(row[field]) > direction * Number(top[field]) ? row : top), null);

function TrendCard({ primary, secondary, onSecondary, localities }) {
  const first = useAsync(() => api.market.trend(primary), [primary]);
  const second = useAsync(() => (secondary ? api.market.trend(secondary) : Promise.resolve([])), [secondary]);
  const series = [{ name: primary, points: first.data ?? [] }, ...(secondary ? [{ name: secondary, points: second.data ?? [] }] : [])];
  return (
    <Card
      title="Price index over time"
      action={
        <label className="flex items-center gap-2 text-sm text-slate-600">
          Compare with
          <select value={secondary} onChange={(event) => onSecondary(event.target.value)} className="rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-sm text-navy-900">
            <option value="">No comparison</option>
            {localities.filter((item) => item.locality !== primary).map((item) => (
              <option key={item.locality} value={item.locality}>{item.locality}</option>
            ))}
          </select>
        </label>
      }
    >
      <ErrorNote error={first.error || second.error} />
      {first.loading && !first.data ? <Spinner label="Loading the index" /> : <IndexComparison series={series} label={secondary ? `Price index for ${primary} compared with ${secondary}` : `Price index for ${primary}`} />}
      <p className="mt-2 text-xs text-slate-500">An index shows how prices moved relative to their starting point, not how expensive a locality is. Past movement does not predict future prices.</p>
    </Card>
  );
}

function Overview({ data }) {
  const [params, setParams] = useSearchParams();
  const [city, setCity] = useState(params.get("city") ?? "");
  const [rank, setRank] = useState("change_12m_pct");
  const rows = useMemo(() => {
    const filtered = data.localities.filter((row) => !city || row.city === city);
    return [...filtered].sort((a, b) => Number(b[rank] ?? -Infinity) - Number(a[rank] ?? -Infinity));
  }, [data, city, rank]);
  const selected = rows.some((row) => row.locality === params.get("locality")) ? params.get("locality") : rows[0]?.locality;
  const [secondary, setSecondary] = useState("");

  const fastest = best(rows, "change_12m_pct");
  const highestYield = best(rows, "gross_yield_pct");
  const entry = best(rows, "price_per_sqft", -1);
  const peak = best(rows, "price_per_sqft");

  return (
    <div className="space-y-5">
      {data.any_synthetic && (
        <Notice tone="warning">
          <span className="font-medium">This is fictional demo data.</span> It shows how this page works and says nothing about any real market. It runs to {date(data.latest_period)}.
        </Notice>
      )}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat icon={MapPinned} label="Localities" value={rows.length} hint={city || `Across ${data.cities.length} cities`} />
        {fastest && <Stat icon={TrendingUp} label="Fastest 12-month change" value={percent(fastest.change_12m_pct, 1)} hint={fastest.locality} />}
        {highestYield && <Stat icon={Percent} label="Highest gross yield" value={plainPercent(highestYield.gross_yield_pct, 1)} hint={highestYield.locality} />}
        {entry && peak && <Stat icon={Banknote} label="Price per sq ft" value={money(entry.price_per_sqft)} hint={`Lowest, in ${entry.locality}. Highest is ${money(peak.price_per_sqft)}.`} />}
      </div>

      {selected && <TrendCard primary={selected} secondary={secondary} onSecondary={setSecondary} localities={rows} />}

      <Card
        title="Locality comparison"
        action={
          <div className="flex flex-wrap gap-3">
            <label className="flex items-center gap-2 text-sm text-slate-600">
              City
              <select value={city} onChange={(event) => setCity(event.target.value)} className="rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-sm text-navy-900">
                <option value="">All cities</option>
                {data.cities.map((name) => <option key={name} value={name}>{name}</option>)}
              </select>
            </label>
            <label className="flex items-center gap-2 text-sm text-slate-600">
              Rank by
              <select value={rank} onChange={(event) => setRank(event.target.value)} className="rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-sm text-navy-900">
                {RANKINGS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select>
            </label>
          </div>
        }
      >
        <DataTable
          rows={rows}
          rowKey={(row) => `${row.locality}-${row.city}`}
          empty={<Empty title="No localities in this city" />}
          columns={[
            {
              header: "Locality",
              cell: (row) => (
                <button type="button" aria-pressed={row.locality === selected} onClick={() => setParams({ locality: row.locality })} className={`text-left font-medium underline-offset-2 hover:underline ${row.locality === selected ? "text-teal-700" : "text-navy-900"}`}>
                  {row.locality}
                  <span className="block text-xs font-normal text-slate-500">{row.city}</span>
                </button>
              ),
            },
            { header: "Median price per sq ft", cell: (row) => <span className="tabular">{money(row.price_per_sqft)}</span> },
            { header: "12-month change", cell: (row) => <span className="tabular">{percent(row.change_12m_pct, 1)}</span> },
            { header: "5-year growth per year", cell: (row) => <span className="tabular">{percent(row.cagr_5y_pct, 1)}</span> },
            { header: "Gross yield", cell: (row) => <span className="tabular">{plainPercent(row.gross_yield_pct, 1)}</span> },
            {
              header: "Listings",
              cell: (row) => (row.active_listings ? <Link className="text-teal-700 underline" to={`/properties?q=${encodeURIComponent(row.locality)}`}>{row.active_listings} listed</Link> : <span className="text-slate-500">None</span>),
            },
          ]}
        />
      </Card>

      <Card title="How to read these figures">
        <dl className="grid gap-4 text-sm sm:grid-cols-3">
          <div>
            <dt className="font-medium text-navy-900">Median price per sq ft</dt>
            <dd className="mt-0.5 text-slate-600">The middle price paid per square foot in the latest month. It is useful for comparing properties of different sizes.</dd>
          </div>
          <div>
            <dt className="font-medium text-navy-900">Growth figures</dt>
            <dd className="mt-0.5 text-slate-600">12-month change compares the latest index with a year earlier. 5-year growth is the average yearly rate over five years.</dd>
          </div>
          <div>
            <dt className="flex items-center gap-1.5 font-medium text-navy-900">
              Gross yield <InfoTip label="gross yield">Rent is before costs, vacancy and tax, so the yield you would actually receive is lower.</InfoTip>
            </dt>
            <dd className="mt-0.5 text-slate-600">A year of median rent as a percentage of the median price.</dd>
          </div>
        </dl>
      </Card>
      <div className="flex justify-end">
        <Link to="/properties"><Button variant="secondary">Browse listings</Button></Link>
      </div>
    </div>
  );
}

export default function MarketPage() {
  const state = useAsync(() => api.market.localities(), []);
  return (
    <>
      <PageHeader title="Market insights" subtitle="Compare localities on price, growth and rental yield, before you look at a single listing." action={state.data?.any_synthetic ? <SyntheticBadge /> : null} />
      <PageGuide id="market" steps={["Rank the table by what matters to you, such as yield or recent growth.", "Select a locality to chart its price index, and add a second one to compare them.", "Follow a locality's listings link to see what is for sale there."]} />
      <Loadable state={state} label="Loading market data">
        {(data) => (data.localities.length ? <Overview data={data} /> : <Empty title="No market data has been loaded">An administrator can load licensed market data. The Help center explains how.</Empty>)}
      </Loadable>
    </>
  );
}
