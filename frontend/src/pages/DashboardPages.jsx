import { ArrowRight, Blocks, Boxes, Building2, Calculator, CheckCircle2, ClipboardList, Coins, Heart, LineChart, Percent, Sparkles, TrendingUp } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { GettingStarted, PageGuide } from "../components/guide";
import { PricePositionBadge } from "../components/insights";
import { ModelBadge, PropertyCard } from "../components/property";
import { Badge, Button, Card, ClaimBadge, ConfirmDialog, DataTable, Empty, ErrorNote, Loadable, Notice, PageHeader, Pagination, Stat, StatusBadge, SyntheticBadge, TextAreaField } from "../components/ui";
import { useAction, useAsync } from "../hooks/useAsync";
import { useAuth } from "../hooks/useAuth";
import { api } from "../services/api";
import { compactMoney, date, dateTime, displayTitle, money, percent, plainPercent, shortHash, titleCase } from "../utils/format";

function ModelNotice({ model, freshness }) {
  return (
    <Card title="Model and data">
      <div className="flex flex-wrap items-center gap-2">
        <ModelBadge model={model} />
        {model.trained_on_synthetic_data && <SyntheticBadge />}
      </div>
      {!model.available && <p className="mt-2 text-sm text-slate-600">No approved model is active, so valuations are unavailable. No estimates are being made up in its place.</p>}
      <dl className="mt-3 space-y-1 text-sm text-slate-700">
        <div><dt className="inline text-slate-500">Model trained: </dt><dd className="inline">{date(model.trained_at)}</dd></div>
        <div><dt className="inline text-slate-500">Latest market data: </dt><dd className="inline">{date(freshness.latest_market_period)}{freshness.market_data_is_synthetic ? " (synthetic)" : ""}</dd></div>
        <div><dt className="inline text-slate-500">Your latest estimate: </dt><dd className="inline">{dateTime(freshness.last_valuation_at)}</dd></div>
      </dl>
    </Card>
  );
}

function MarketSnapshot() {
  const state = useAsync(() => api.market.localities().catch(() => null), []);
  const rows = state.data?.localities ?? [];
  if (!rows.length) return null;
  const top = [...rows].sort((a, b) => Number(b.change_12m_pct ?? -Infinity) - Number(a.change_12m_pct ?? -Infinity)).slice(0, 5);
  return (
    <Card title="Fastest-moving localities" action={<Link to="/market" className="inline-flex items-center gap-1 text-sm font-medium text-teal-700">All market insights <ArrowRight aria-hidden className="h-3.5 w-3.5" /></Link>} className="lg:col-span-2">
      {state.data.any_synthetic && <div className="mb-3"><SyntheticBadge /></div>}
      <DataTable
        rows={top}
        rowKey={(row) => row.locality}
        columns={[
          { header: "Locality", cell: (row) => <Link className="font-medium text-navy-900 hover:text-teal-700" to={`/market?locality=${encodeURIComponent(row.locality)}`}>{row.locality}</Link> },
          { header: "12-month change", cell: (row) => <span className="tabular">{percent(row.change_12m_pct, 1)}</span> },
          { header: "Price per sq ft", cell: (row) => <span className="tabular">{money(row.price_per_sqft)}</span> },
          { header: "Gross yield", cell: (row) => <span className="tabular">{plainPercent(row.gross_yield_pct, 1)}</span> },
        ]}
      />
    </Card>
  );
}

const QUICK_ACTIONS = [
  { to: "/properties/new", label: "Register a property", icon: Building2, roles: ["owner", "admin"] },
  { to: "/properties", label: "Browse listings", icon: Heart, roles: ["investor"] },
  { to: "/valuations", label: "Get an AI estimate", icon: Sparkles, roles: ["owner", "investor", "admin"] },
  { to: "/verifier", label: "Open the review queue", icon: ClipboardList, roles: ["verifier", "admin"] },
  { to: "/market", label: "Compare localities", icon: LineChart },
  { to: "/calculator", label: "Calculate returns", icon: Calculator, roles: ["owner", "investor", "admin"] },
];

function QuickActions({ roles }) {
  const actions = QUICK_ACTIONS.filter((item) => !item.roles || item.roles.some((role) => roles.includes(role)));
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
      {actions.slice(0, 5).map(({ to, label, icon: Icon }) => (
        <Link key={to} to={to} className="flex items-center gap-2.5 rounded-xl border border-slate-200 bg-white px-3 py-3 text-sm font-medium text-navy-900 shadow-card transition-colors hover:border-teal-600">
          <Icon aria-hidden className="h-4 w-4 shrink-0 text-teal-700" /> {label}
        </Link>
      ))}
    </div>
  );
}

export function DashboardPage() {
  const { user } = useAuth();
  const state = useAsync(() => api.dashboard(), []);
  const isOwner = user.roles.includes("owner");
  return (
    <>
      <PageHeader title={`Welcome, ${user.display_name}`} subtitle="Your properties, estimates, scenarios and blockchain activity." />
      <Loadable state={state} label="Loading dashboard">
        {(data) => (
          <div className="space-y-5">
            <GettingStarted onboarding={data.onboarding} />
            <QuickActions roles={user.roles} />
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <Stat icon={Building2} label="Properties" value={data.properties_accessible} hint={isOwner ? "That you manage" : "Available to you"} />
              <Stat icon={Boxes} label="Active digital twins" value={data.active_twins} hint={data.active_twins ? undefined : "Create one to run scenarios"} />
              <Stat icon={ClipboardList} label="Pending verifications" value={data.pending_verifications} hint={user.roles.includes("verifier") ? "Waiting for a decision" : "Waiting for a verifier"} />
              <Stat icon={Heart} label="Saved favorites" value={data.saved_properties} />
            </div>
            <div className="grid gap-4 lg:grid-cols-3">
              <MarketSnapshot />
              <ModelNotice model={data.model} freshness={data.data_freshness} />
            </div>
            <div className="grid gap-4 lg:grid-cols-2">
              <Card title="Latest valuations" action={<ClaimBadge kind="ai" />}>
                <DataTable
                  rows={data.latest_valuations}
                  rowKey={(row) => row.id}
                  empty={<Empty title="No estimates yet" action={<Link to="/valuations" className="font-medium text-teal-700">Request a valuation</Link>} />}
                  columns={[
                    { header: "Property", cell: (row) => (row.property_id ? <Link className="text-teal-700 underline" to={`/properties/${row.property_id}`}>{row.property_title}</Link> : "Entered manually") },
                    { header: "Estimate", cell: (row) => <span className="tabular">{money(row.predicted_value, row.currency)}</span> },
                    { header: "When", cell: (row) => date(row.predicted_at) },
                  ]}
                />
              </Card>
              <Card title="Recent simulations" action={<ClaimBadge kind="hypothetical" />}>
                <DataTable
                  rows={data.recent_simulations}
                  rowKey={(row) => row.id}
                  empty={<Empty title="No scenarios yet" action={<Link to="/simulator" className="font-medium text-teal-700">Open the simulator</Link>}>Test a market change or renovation without touching the real record.</Empty>}
                  columns={[
                    { header: "Scenario", cell: (row) => row.name },
                    { header: "Scenario value", cell: (row) => <span className="tabular">{money(row.scenario_value)}</span> },
                    { header: "Difference", cell: (row) => <span className="tabular">{percent(row.percentage_difference)}</span> },
                  ]}
                />
              </Card>
            </div>
            <Card title="Recent blockchain transactions">
              <DataTable
                rows={data.recent_transactions}
                rowKey={(row) => row.id}
                empty={<Empty title="No transactions yet">Committing a property's record creates a tamper-evident hash, and it will show here.</Empty>}
                columns={[
                  { header: "Operation", cell: (row) => titleCase(row.operation) },
                  { header: "Status", cell: (row) => <StatusBadge status={row.status} /> },
                  { header: "Transaction", cell: (row) => <span className="font-mono text-xs">{shortHash(row.tx_hash)}</span> },
                  { header: "Property", cell: (row) => <Link className="text-teal-700 underline" to={`/properties/${row.property_id}/blockchain`}>View</Link> },
                  { header: "When", cell: (row) => dateTime(row.created_at) },
                ]}
              />
            </Card>
          </div>
        )}
      </Loadable>
    </>
  );
}

export function OwnerDashboardPage() {
  const state = useAsync(() => api.properties.portfolio(), []);
  return (
    <>
      <PageHeader
        title="My properties"
        subtitle="Your portfolio's value, income and record status, with the next step for each property."
        action={<Link to="/properties/new" className="rounded-lg bg-teal-700 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-teal-600">Register a property</Link>}
      />
      <Loadable state={state} label="Loading properties">
        {(data) =>
          data.items.length === 0 ? (
            <Empty title="You have not registered a property" action={<Link className="font-medium text-teal-700" to="/properties/new">Register your first property</Link>}>Once you do, its estimate, status and next step will show here.</Empty>
          ) : (
            <div className="space-y-4">
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <Stat icon={Coins} label="Total AI-estimated value" value={data.total_estimate === null ? "Mixed currencies" : compactMoney(data.total_estimate, data.currency)} hint={`${data.estimated_count} of ${data.total_properties} properties have an estimate`} badge={<ClaimBadge kind="ai" />} />
                <Stat icon={TrendingUp} label="Annual rent on record" value={data.total_annual_rent === null ? "Mixed currencies" : compactMoney(data.total_annual_rent, data.currency)} hint="Before costs and vacancy" />
                <Stat icon={CheckCircle2} label="Verified" value={`${data.verified_count} of ${data.total_properties}`} hint={`${data.twin_count} with a digital twin`} />
                <Stat icon={Blocks} label="On the blockchain" value={`${data.on_chain_count} of ${data.total_properties}`} hint={data.action_count ? `${data.action_count} properties have a next step` : "All steps are complete"} />
              </div>
              {data.truncated && <Notice>Showing the newest {data.items.length} of {data.total_properties} properties. Totals cover only these.</Notice>}
              <Card>
                <DataTable
                  rows={data.items}
                  rowKey={(row) => row.id}
                  columns={[
                    {
                      header: "Property",
                      cell: (row) => (
                        <>
                          <Link className="font-medium text-teal-700 underline" to={`/properties/${row.id}`}>{displayTitle(row)}</Link>
                          <span className="mt-0.5 block text-xs text-slate-500">{[row.locality, row.city].filter(Boolean).join(", ")}</span>
                        </>
                      ),
                    },
                    { header: "Listing", cell: (row) => <StatusBadge status={row.listing_status} /> },
                    { header: "Verification", cell: (row) => <StatusBadge status={row.verification_status} /> },
                    { header: "Asking price", cell: (row) => <span className="tabular">{money(row.asking_price, row.currency)}</span> },
                    {
                      header: "AI estimate",
                      cell: (row) =>
                        row.estimate ? (
                          <>
                            <span className="tabular">{money(row.estimate, row.currency)}</span>
                            {!row.estimate_current && <span className="block text-xs text-amber-800">Out of date</span>}
                          </>
                        ) : (
                          <span className="text-slate-500">None yet</span>
                        ),
                    },
                    {
                      header: "Next step",
                      cell: (row) =>
                        row.next_action ? (
                          <Link className="inline-flex items-center gap-1 whitespace-nowrap font-medium text-teal-700" to={row.next_action.href} title={row.next_action.reason}>
                            {row.next_action.label} <ArrowRight aria-hidden className="h-3.5 w-3.5" />
                          </Link>
                        ) : (
                          <span className="inline-flex items-center gap-1 text-slate-600"><CheckCircle2 aria-hidden className="h-3.5 w-3.5 text-teal-700" /> All done</span>
                        ),
                    },
                    {
                      header: "Tools",
                      cell: (row) => (
                        <div className="flex flex-wrap gap-3 text-sm">
                          <Link className="text-teal-700 underline" to={`/valuations?property=${row.id}`}>Value</Link>
                          <Link className="text-teal-700 underline" to={`/properties/${row.id}/twin`}>Twin</Link>
                          <Link className="text-teal-700 underline" to={`/properties/${row.id}/blockchain`}>Blockchain</Link>
                        </div>
                      ),
                    },
                  ]}
                />
              </Card>
            </div>
          )
        }
      </Loadable>
    </>
  );
}

export function InvestorDashboardPage() {
  const favorites = useAsync(async () => {
    const items = await api.favorites.list();
    // A missing comparison must not hide the shortlist, so each lookup can fail by itself.
    const insights = await Promise.all(items.map((item) => api.properties.insights(item.id).catch(() => null)));
    return items.map((item, index) => ({ ...item, insights: insights[index] }));
  }, []);
  const remove = useAction(async (id) => {
    await api.favorites.remove(id);
    favorites.reload();
  });
  return (
    <>
      <PageHeader
        title="Investments"
        subtitle="Your saved listings with their prices and yields checked. Yields here are simple arithmetic, not forecasts."
        action={<Link to="/properties" className="rounded-lg bg-teal-700 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-teal-600">Browse listings</Link>}
      />
      <PageGuide id="investor" steps={["Save listings from Properties to build your shortlist here.", "Compare the yield and price check. A price above the estimate's range is worth questioning.", "Simulate a market fall, or calculate returns with your own loan terms."]} />
      <ErrorNote error={remove.error} />
      <Loadable state={favorites} label="Loading favorites">
        {(items) =>
          items.length === 0 ? (
            <Empty title="No saved listings" action={<Link className="font-medium text-teal-700" to="/properties">Browse listings</Link>}>Save a listing to compare it and run scenarios here.</Empty>
          ) : (
            <div className="space-y-4">
              <Card title="Estimated rental yield and price check">
                <DataTable
                  rows={items}
                  rowKey={(row) => row.id}
                  columns={[
                    { header: "Property", cell: (row) => <Link className="text-teal-700 underline" to={`/properties/${row.id}`}>{displayTitle(row)}</Link> },
                    { header: "Asking price", cell: (row) => <span className="tabular">{money(row.asking_price, row.currency)}</span> },
                    { header: "Monthly rent", cell: (row) => <span className="tabular">{money(row.monthly_rent, row.currency)}</span> },
                    {
                      header: "Gross yield",
                      cell: (row) => (
                        <span className="tabular">
                          {row.insights?.gross_yield_pct ? plainPercent(row.insights.gross_yield_pct) : "Not available"}
                          {row.insights?.market_yield_pct && <span className="block text-xs text-slate-500">Locality {plainPercent(row.insights.market_yield_pct)}</span>}
                        </span>
                      ),
                    },
                    { header: "Price check", cell: (row) => (row.insights?.price_position ? <PricePositionBadge position={row.insights.price_position} /> : <span className="text-slate-500">No estimate yet</span>) },
                    {
                      header: "Tools",
                      cell: (row) => (
                        <div className="flex flex-wrap gap-3">
                          <Link className="text-teal-700 underline" to={`/simulator?property=${row.id}`}>Simulate</Link>
                          <Link className="text-teal-700 underline" to={`/calculator?property=${row.id}`}>Returns</Link>
                        </div>
                      ),
                    },
                  ]}
                />
              </Card>
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {items.map((property) => (
                  <PropertyCard key={property.id} property={property} saved onToggleSaved={(id) => remove.run(id)} />
                ))}
              </div>
            </div>
          )
        }
      </Loadable>
    </>
  );
}

function DecisionDialog({ request, decision, onClose, onDone }) {
  const [notes, setNotes] = useState("");
  const submit = useAction(async () => {
    await api.verification.decide(request.id, { decision, notes });
    onDone();
  });
  return (
    <ConfirmDialog open title={decision === "approved" ? "Approve this request?" : "Reject this request?"} confirmLabel={decision === "approved" ? "Approve" : "Reject"} tone={decision === "approved" ? "primary" : "danger"} busy={submit.busy} error={submit.error} onCancel={onClose} onConfirm={() => submit.run()}>
      <p className="mb-3">Your decision and notes are recorded permanently against your account.</p>
      <TextAreaField label="Decision notes" value={notes} onChange={(event) => setNotes(event.target.value)} />
    </ConfirmDialog>
  );
}

export function VerifierDashboardPage() {
  const [status, setStatus] = useState("pending");
  const [page, setPage] = useState(1);
  const queue = useAsync(() => api.verification.queue({ status, page, page_size: 20 }), [status, page]);
  const [deciding, setDeciding] = useState(null);
  return (
    <>
      <PageHeader title="Verification queue" subtitle="Review submitted documents and record a decision. A decision records your review. It is not a legal title determination." />
      <PageGuide id="verifier" steps={["Open a pending request's property, and download its documents.", "Check that they match the record. You cannot review a property you own.", "Approve or reject it with a note. Your decision is kept against your name, and the owner is told."]} />
      <div className="mb-4 flex gap-2" role="group" aria-label="Filter by status">
        {["pending", "approved", "rejected"].map((value) => (
          <Button
            key={value}
            variant={status === value ? "primary" : "secondary"}
            onClick={() => {
              setStatus(value);
              setPage(1);
            }}
          >
            {titleCase(value)}
          </Button>
        ))}
      </div>
      <Loadable state={queue} label="Loading queue">
        {(data) => (
          <Card>
            <DataTable
              rows={data.items}
              rowKey={(row) => row.id}
              empty={<Empty title={`No ${status} requests`} />}
              columns={[
                { header: "Property", cell: (row) => <><Link className="font-medium text-teal-700 underline" to={`/properties/${row.property_id}#verification`}>{row.property_title ?? "Review property"}</Link><span className="mt-0.5 block text-xs text-slate-500">Open to read its documents</span></> },
                { header: "Submitted", cell: (row) => dateTime(row.created_at) },
                { header: "Owner's note", cell: (row) => row.request_notes ?? "None" },
                { header: "Status", cell: (row) => <StatusBadge status={row.status} /> },
                {
                  header: status === "pending" ? "Decision" : "Notes",
                  cell: (row) =>
                    row.status === "pending" ? (
                      <div className="flex gap-2">
                        <Button onClick={() => setDeciding({ request: row, decision: "approved" })}>Approve</Button>
                        <Button variant="secondary" onClick={() => setDeciding({ request: row, decision: "rejected" })}>Reject</Button>
                      </div>
                    ) : (
                      row.decision_notes
                    ),
                },
              ]}
            />
            <Pagination page={data.page} pageSize={data.page_size} total={data.total} onChange={setPage} />
          </Card>
        )}
      </Loadable>
      {deciding && (
        <DecisionDialog
          {...deciding}
          onClose={() => setDeciding(null)}
          onDone={() => {
            setDeciding(null);
            queue.reload();
          }}
        />
      )}
    </>
  );
}

const ROLE_OPTIONS = ["owner", "investor", "verifier", "admin"];

function UsersTab() {
  const { user: me } = useAuth();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const state = useAsync(() => api.admin.users({ page, page_size: 20, ...(query ? { q: query } : {}) }), [page, query]);
  const [pending, setPending] = useState(null);
  const update = useAction(async () => {
    await api.admin.updateUser(pending.user.id, pending.changes);
    setPending(null);
    state.reload();
  });
  return (
    <Loadable state={state} label="Loading users">
      {(data) => (
        <Card title="Users">
          <form
            className="mb-4 flex flex-wrap items-end gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              setPage(1);
              setQuery(search.trim());
            }}
          >
            <label className="text-sm font-medium text-navy-800">
              Find a user
              <input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Name or email" className="mt-1 block w-64 max-w-full rounded-md border border-slate-300 px-3 py-2 text-sm font-normal" />
            </label>
            <Button type="submit" variant="secondary">Search</Button>
          </form>
          <DataTable
            rows={data.items}
            rowKey={(row) => row.id}
            columns={[
              { header: "User", cell: (row) => <><p className="font-medium">{row.display_name}</p><p className="text-xs text-slate-500">{row.email}</p></> },
              {
                header: "Roles",
                cell: (row) => (
                  <div className="flex flex-wrap gap-2">
                    {ROLE_OPTIONS.map((role) => (
                      <label key={role} className="flex items-center gap-1 text-xs">
                        <input
                          type="checkbox"
                          checked={row.roles.includes(role)}
                          disabled={row.id === me.id}
                          onChange={(event) =>
                            setPending({
                              user: row,
                              summary: `${event.target.checked ? "Grant" : "Remove"} the ${role} role for ${row.email}?`,
                              changes: { roles: event.target.checked ? [...row.roles, role] : row.roles.filter((item) => item !== role) },
                            })
                          }
                        />
                        {role}
                      </label>
                    ))}
                  </div>
                ),
              },
              { header: "Status", cell: (row) => <Badge tone={row.is_active ? "teal" : "red"}>{row.is_active ? "Active" : "Deactivated"}</Badge> },
              {
                header: "",
                cell: (row) =>
                  row.id === me.id ? (
                    <span className="text-xs text-slate-500">This is you</span>
                  ) : (
                    <Button variant="secondary" onClick={() => setPending({ user: row, summary: `${row.is_active ? "Deactivate" : "Reactivate"} ${row.email}?${row.is_active ? " This ends their sessions immediately." : ""}`, changes: { is_active: !row.is_active } })}>
                      {row.is_active ? "Deactivate" : "Reactivate"}
                    </Button>
                  ),
              },
            ]}
          />
          <Pagination page={data.page} pageSize={data.page_size} total={data.total} onChange={setPage} />
          <ConfirmDialog open={Boolean(pending)} title="Confirm account change" busy={update.busy} error={update.error} onCancel={() => setPending(null)} onConfirm={() => update.run()}>
            {pending?.summary}
          </ConfirmDialog>
        </Card>
      )}
    </Loadable>
  );
}

function ModelsTab() {
  const state = useAsync(() => api.admin.models(), []);
  const [detail, setDetail] = useState(null);
  const [pending, setPending] = useState(null);
  const promote = useAction(async () => {
    await api.admin.promoteModel(pending.version, pending.target);
    setPending(null);
    state.reload();
  });
  const showMetrics = useAction(async (version) => setDetail(await api.admin.modelMetrics(version)));
  const NEXT = { candidate: ["approved", "rejected"], approved: ["active", "rejected"], active: ["retired"], retired: ["approved"] };
  const held = detail?.metrics.held_out_test;
  return (
    <Loadable state={state} label="Loading models">
      {(models) => (
        <div className="space-y-4">
          <Card title="Model versions">
            <ErrorNote error={showMetrics.error} />
            <DataTable
              rows={models}
              rowKey={(row) => row.version}
              empty={<Empty title="No trained models found">Run the training command in ml/README.md.</Empty>}
              columns={[
                { header: "Version", cell: (row) => <button type="button" className="text-left font-mono text-xs text-teal-700 underline" onClick={() => showMetrics.run(row.version)}>{row.version}</button> },
                { header: "Status", cell: (row) => <StatusBadge status={row.status} /> },
                { header: "Held-out MAE", cell: (row) => <span className="tabular">{money(row.headline_metrics.mae)}</span> },
                { header: "R²", cell: (row) => <span className="tabular">{row.headline_metrics.r2.toFixed(3)}</span> },
                { header: "Beat baseline", cell: (row) => <Badge tone={row.beats_baseline ? "teal" : "red"}>{row.beats_baseline ? "Yes" : "No"}</Badge> },
                { header: "Data", cell: (row) => (row.trained_on_synthetic_data ? <SyntheticBadge /> : "Real") },
                {
                  header: "Actions",
                  cell: (row) => (
                    <div className="flex flex-wrap gap-2">
                      {(NEXT[row.status] ?? []).map((target) => (
                        <Button key={target} variant="secondary" onClick={() => setPending({ version: row.version, target })}>
                          {titleCase(target === "active" ? "activate" : target === "approved" ? "approve" : target === "rejected" ? "reject" : "retire")}
                        </Button>
                      ))}
                    </div>
                  ),
                },
              ]}
            />
          </Card>
          {detail && (
            <Card title={`Evaluation of ${detail.version}`}>
              <DataTable
                rows={Object.entries(held)}
                rowKey={(row) => row[0]}
                columns={[
                  { header: "Model", cell: ([name]) => titleCase(name) },
                  { header: "MAE", cell: ([, values]) => <span className="tabular">{money(values.mae)}</span> },
                  { header: "RMSE", cell: ([, values]) => <span className="tabular">{money(values.rmse)}</span> },
                  { header: "R²", cell: ([, values]) => <span className="tabular">{values.r2.toFixed(3)}</span> },
                  { header: "MAPE", cell: ([, values]) => <span className="tabular">{values.mape_pct.toFixed(1)}%</span> },
                ]}
              />
              <p className="mt-3 text-sm text-slate-600">
                Measured on {detail.metrics.split.test_rows} held-out rows from {detail.metrics.split.test_start} to {detail.metrics.split.test_end} ({detail.metrics.split.strategy} split). The {Math.round(detail.metrics.interval.nominal_coverage * 100)}% range covered {(detail.metrics.interval.empirical_test_coverage * 100).toFixed(1)}% of them.
              </p>
            </Card>
          )}
          <ConfirmDialog open={Boolean(pending)} title="Change model status" busy={promote.busy} error={promote.error} onCancel={() => setPending(null)} onConfirm={() => promote.run()}>
            Set {pending?.version} to {pending?.target}? {pending?.target === "active" && "All new estimates will use this model, and the current active model will be retired."}
          </ConfirmDialog>
        </div>
      )}
    </Loadable>
  );
}

function ReportsTab() {
  const state = useAsync(() => api.admin.reports({ status: "open", page_size: 50 }), []);
  const resolve = useAction(async (id, body) => {
    await api.admin.resolveReport(id, body);
    state.reload();
  });
  return (
    <Loadable state={state} label="Loading reports">
      {(data) => (
        <Card title="Reported listings">
          <ErrorNote error={resolve.error} />
          <DataTable
            rows={data.items}
            rowKey={(row) => row.id}
            empty={<Empty title="No open reports" />}
            columns={[
              { header: "Listing", cell: (row) => <Link className="text-teal-700 underline" to={`/properties/${row.property_id}`}>View</Link> },
              { header: "Reason", cell: (row) => row.reason },
              { header: "Reported", cell: (row) => dateTime(row.created_at) },
              {
                header: "Actions",
                cell: (row) => (
                  <div className="flex flex-wrap gap-2">
                    <Button variant="secondary" onClick={() => resolve.run(row.id, { status: "dismissed" })}>Dismiss</Button>
                    <Button variant="danger" onClick={() => resolve.run(row.id, { status: "actioned", archive_listing: true })}>Archive listing</Button>
                  </div>
                ),
              },
            ]}
          />
        </Card>
      )}
    </Loadable>
  );
}

function TransactionsTab() {
  const [page, setPage] = useState(1);
  const state = useAsync(() => api.admin.transactions({ page, page_size: 20 }), [page]);
  return (
    <Loadable state={state} label="Loading transactions">
      {(data) => (
        <Card title="Blockchain transactions">
          <DataTable
            rows={data.items}
            rowKey={(row) => row.id}
            empty={<Empty title="No transactions yet" />}
            columns={[
              { header: "Operation", cell: (row) => titleCase(row.operation) },
              { header: "Status", cell: (row) => <StatusBadge status={row.status} /> },
              { header: "Hash", cell: (row) => <span className="font-mono text-xs">{shortHash(row.tx_hash)}</span> },
              { header: "Block", cell: (row) => row.block_number ?? "Pending" },
              { header: "Failure", cell: (row) => row.failure_reason ?? "None" },
              { header: "Created", cell: (row) => dateTime(row.created_at) },
            ]}
          />
          <Pagination page={data.page} pageSize={data.page_size} total={data.total} onChange={setPage} />
        </Card>
      )}
    </Loadable>
  );
}

function AuditTab() {
  const [page, setPage] = useState(1);
  const state = useAsync(() => api.admin.auditLogs({ page, page_size: 25 }), [page]);
  return (
    <Loadable state={state} label="Loading audit log">
      {(data) => (
        <Card title="Audit log">
          <DataTable
            rows={data.items}
            rowKey={(row) => row.id}
            columns={[
              { header: "When", cell: (row) => dateTime(row.created_at) },
              { header: "Action", cell: (row) => <span className="font-mono text-xs">{row.action}</span> },
              { header: "Entity", cell: (row) => `${row.entity_type}` },
              { header: "Details", cell: (row) => <span className="break-all text-xs text-slate-600">{JSON.stringify(row.details)}</span> },
            ]}
          />
          <Pagination page={data.page} pageSize={data.page_size} total={data.total} onChange={setPage} />
        </Card>
      )}
    </Loadable>
  );
}

function MonitoringTab() {
  const state = useAsync(() => api.admin.monitoring(), []);
  return (
    <Loadable state={state} label="Loading monitoring">
      {(data) => (
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-3">
            <Stat label="Users" value={data.users} />
            <Stat label="Properties" value={data.properties} />
            <Stat label="Predictions scored" value={data.prediction.predictions_scored} hint="By the active model" />
          </div>
          <Card title="Prediction drift">
            {data.prediction.drift ? (
              <p className="text-sm">
                Population stability index: <span className="tabular font-semibold">{data.prediction.drift.value}</span> <StatusBadge status={data.prediction.drift.status} />
              </p>
            ) : (
              <p className="text-sm text-slate-600">{data.prediction.drift_note ?? "No active model."}</p>
            )}
            <p className="mt-2 text-xs text-slate-500">This compares recent estimates with the training prices. Sale outcomes are not collected, so it measures drift rather than accuracy.</p>
          </Card>
          <Card title="Blockchain network">
            <p className="text-sm">
              {data.blockchain.network}: <Badge tone={data.blockchain.reachable ? "teal" : "red"}>{data.blockchain.reachable ? "Reachable" : "Not reachable"}</Badge>
            </p>
            {data.transactions.length > 0 && <p className="mt-2 text-sm text-slate-600">{data.transactions.map((item) => `${item.count} ${item.status}`).join(", ")}</p>}
          </Card>
          <Card title="Background jobs">
            {data.jobs.length ? <p className="text-sm text-slate-600">{data.jobs.map((item) => `${item.count} ${item.status}`).join(", ")}</p> : <p className="text-sm text-slate-600">No jobs recorded.</p>}
            {data.dead_jobs.length > 0 && (
              <div className="mt-3">
                <Notice tone="warning">
                  <p className="font-medium">Jobs that gave up after retrying</p>
                  <ul className="mt-1 space-y-1">
                    {data.dead_jobs.map((job) => (
                      <li key={job.id}>{job.kind}: {job.last_error}</li>
                    ))}
                  </ul>
                </Notice>
              </div>
            )}
          </Card>
        </div>
      )}
    </Loadable>
  );
}

const ADMIN_TABS = { Users: UsersTab, Models: ModelsTab, Reports: ReportsTab, Transactions: TransactionsTab, "Audit log": AuditTab, Monitoring: MonitoringTab };

export function AdminDashboardPage() {
  const [tab, setTab] = useState("Users");
  const Tab = ADMIN_TABS[tab];
  return (
    <>
      <PageHeader title="Administration" subtitle="Accounts, model approval, reports, transactions, audit trail and system health." />
      <div role="tablist" aria-label="Administration sections" className="mb-4 flex flex-wrap gap-1 border-b border-slate-200">
        {Object.keys(ADMIN_TABS).map((name) => (
          <button key={name} role="tab" type="button" aria-selected={tab === name} onClick={() => setTab(name)} className={`border-b-2 px-3 py-2 text-sm font-medium ${tab === name ? "border-teal-700 text-teal-700" : "border-transparent text-slate-600 hover:text-navy-900"}`}>
            {name}
          </button>
        ))}
      </div>
      <Tab />
    </>
  );
}
