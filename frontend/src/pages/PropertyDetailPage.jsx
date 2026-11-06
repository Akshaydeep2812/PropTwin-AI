import { Blocks, Boxes, Calculator, FileText, Flag, MapPin, Pencil, Sparkles, Trash2, Upload } from "lucide-react";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { TrendChart } from "../components/charts";
import { DecisionSnapshot, PropertyJourney } from "../components/insights";
import { PropertyArt, PropertyImage } from "../components/property";
import { Button, Card, ClaimBadge, ConfirmDialog, DataTable, Empty, ErrorNote, KeyValues, Loadable, Notice, PageHeader, StatusBadge, SuccessNote, SyntheticBadge, TextAreaField, TextField } from "../components/ui";
import { useAction, useAsync } from "../hooks/useAsync";
import { useAuth } from "../hooks/useAuth";
import { api } from "../services/api";
import { area, date, dateTime, displayTitle, downloadBlob, money, shortHash, titleCase } from "../utils/format";

function ImagesCard({ property, canManage, onChanged }) {
  const upload = useAction(async (file) => {
    await api.properties.uploadImage(property.id, file);
    onChanged();
  });
  if (!canManage && property.images.length < 2) return null;
  return (
    <Card
      title="Images"
      action={
        canManage && (
          <label className="inline-flex cursor-pointer items-center gap-2 rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-navy-900 hover:bg-slate-50">
            <Upload aria-hidden className="h-4 w-4" />
            {upload.busy ? "Uploading…" : "Add image"}
            <input type="file" accept="image/jpeg,image/png,image/webp" className="sr-only" onChange={(event) => event.target.files[0] && upload.run(event.target.files[0])} />
          </label>
        )
      }
    >
      <ErrorNote error={upload.error} />
      {property.images.length ? (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {property.images.map((image) => (
            <PropertyImage key={image.id} propertyId={property.id} image={image} alt={property.title} className="h-28 w-full rounded-md" />
          ))}
        </div>
      ) : (
        <Empty title="No images yet" />
      )}
    </Card>
  );
}

function VerificationCard({ property, canManage, onChanged }) {
  const documents = useAsync(() => (property.access_level === "full" ? api.properties.documents(property.id) : Promise.resolve([])), [property.id]);
  const history = useAsync(() => (property.access_level === "full" ? api.properties.verificationHistory(property.id) : Promise.resolve([])), [property.id]);
  const [documentType, setDocumentType] = useState("sale_deed");
  const upload = useAction(async (file) => {
    await api.properties.uploadDocument(property.id, file, documentType);
    documents.reload();
  });
  const request = useAction(async () => {
    await api.properties.requestVerification(property.id, null);
    history.reload();
    onChanged();
  });
  const download = useAction(async (document) => downloadBlob(await api.properties.documentBlob(property.id, document.id), document.original_filename));

  return (
    <Card title="Verification" action={<StatusBadge status={property.verification_status} />}>
      <p className="mb-3 text-sm text-slate-600">
        <ClaimBadge kind="document" /> A verifier's decision records that a person reviewed these files. It is not a legal title search.
      </p>
      {property.access_level !== "full" ? (
        <p className="text-sm text-slate-600">Documents are visible only to the owner and verifiers.</p>
      ) : (
        <>
          <ErrorNote error={upload.error || request.error || download.error} />
          <DataTable
            rows={documents.data ?? []}
            rowKey={(row) => row.id}
            empty={<Empty title="No documents uploaded">{canManage ? "Upload at least one document to request verification." : undefined}</Empty>}
            columns={[
              { header: "Document", cell: (row) => row.original_filename },
              { header: "Type", cell: (row) => titleCase(row.document_type) },
              { header: "Uploaded", cell: (row) => dateTime(row.created_at) },
              { header: "", cell: (row) => <button type="button" className="font-medium text-teal-700 underline" onClick={() => download.run(row)}>Download</button> },
            ]}
          />
          {canManage && (
            <div className="mt-4 flex flex-wrap items-end gap-2">
              <label className="text-sm font-medium text-navy-800">
                Document type
                <select value={documentType} onChange={(event) => setDocumentType(event.target.value)} className="mt-1 block rounded-md border border-slate-300 px-3 py-2 text-sm font-normal">
                  <option value="sale_deed">Sale deed</option>
                  <option value="tax_receipt">Tax receipt</option>
                  <option value="survey_plan">Survey plan</option>
                  <option value="other">Other</option>
                </select>
              </label>
              <label className="inline-flex cursor-pointer items-center gap-2 rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-navy-900 hover:bg-slate-50">
                <Upload aria-hidden className="h-4 w-4" />
                {upload.busy ? "Uploading…" : "Upload PDF or image"}
                <input type="file" accept="application/pdf,image/jpeg,image/png,image/webp" className="sr-only" onChange={(event) => event.target.files[0] && upload.run(event.target.files[0])} />
              </label>
              <Button onClick={() => request.run()} busy={request.busy} disabled={property.verification_status === "pending" || !documents.data?.length}>
                Request verification
              </Button>
            </div>
          )}
          {history.data?.length > 0 && (
            <div className="mt-5">
              <h3 className="mb-2 text-sm font-semibold text-navy-900">Decision history</h3>
              <ul className="space-y-2 text-sm">
                {history.data.map((item) => (
                  <li key={item.id} className="rounded-md bg-slate-50 p-3">
                    <StatusBadge status={item.status} /> <span className="text-slate-500">{dateTime(item.decided_at ?? item.created_at)}</span>
                    {item.decision_notes && <p className="mt-1">{item.decision_notes}</p>}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </Card>
  );
}

function RenovationForm({ propertyId, onSaved }) {
  const { register, handleSubmit, reset, formState } = useForm();
  const save = useAction(async ({ description, cost, completed_on }) => {
    await api.properties.addRenovation(propertyId, { description, completed_on, cost: cost ? Number(cost).toFixed(2) : null });
    reset();
    onSaved();
  });
  const errors = formState.errors;
  return (
    <form onSubmit={handleSubmit((values) => save.run(values))} noValidate className="mt-4 grid gap-3 border-t border-slate-100 pt-4 sm:grid-cols-3">
      <div className="sm:col-span-3">
        <ErrorNote error={save.error} />
      </div>
      <TextField label="Work done" registration={register("description", { required: "Describe the work.", minLength: { value: 3, message: "Use at least 3 characters." } })} error={errors.description?.message} />
      <TextField label="Completed on" type="date" registration={register("completed_on", { required: "Enter the date." })} error={errors.completed_on?.message} />
      <TextField label="Cost" type="number" min="0" registration={register("cost", { min: { value: 0, message: "Cannot be negative." } })} error={errors.cost?.message} />
      <div className="sm:col-span-3">
        <Button type="submit" variant="secondary" busy={save.busy}>
          Add renovation
        </Button>
      </div>
    </form>
  );
}

function ReportControl({ propertyId }) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [done, setDone] = useState(false);
  const submit = useAction(async () => {
    await api.properties.report(propertyId, reason);
    setDone(true);
    setOpen(false);
  });
  if (done) return <SuccessNote>Thanks. An administrator will review this listing.</SuccessNote>;
  return (
    <>
      <Button variant="ghost" onClick={() => setOpen(true)}>
        <Flag aria-hidden className="h-4 w-4" /> Report listing
      </Button>
      <ConfirmDialog open={open} title="Report this listing" confirmLabel="Send report" busy={submit.busy} error={submit.error} onCancel={() => setOpen(false)} onConfirm={() => submit.run()}>
        <TextAreaField label="What is wrong with it?" value={reason} onChange={(event) => setReason(event.target.value)} />
      </ConfirmDialog>
    </>
  );
}

export default function PropertyDetailPage() {
  const { id } = useParams();
  const { user } = useAuth();
  const navigate = useNavigate();
  const { hash } = useLocation();
  const state = useAsync(() => api.properties.get(id), [id]);
  const insights = useAsync(() => api.properties.insights(id).catch(() => null), [id, state.data?.updated_at]);
  const valuations = useAsync(() => api.properties.valuations(id, { page_size: 50 }), [id]);
  const twin = useAsync(() => (user ? api.twins.forProperty(id).catch((error) => (error.status === 404 ? null : Promise.reject(error))) : Promise.resolve(null)), [id, user?.id]);
  const chainRecord = useAsync(() => api.chain.record(id).catch((error) => (error.status === 404 ? null : Promise.reject(error))), [id]);
  const [confirmArchive, setConfirmArchive] = useState(false);
  const loaded = Boolean(state.data);
  useEffect(() => {
    if (loaded && hash) document.getElementById(hash.slice(1))?.scrollIntoView?.();
  }, [loaded, hash]);
  const archive = useAction(async () => {
    await api.properties.archive(id);
    navigate("/owner");
  });

  return (
    <Loadable state={state} label="Loading property">
      {(property) => {
        const canManage = property.access_level === "full" && (property.owner_id === user?.id || user?.roles.includes("admin"));
        const latest = valuations.data?.[0];
        return (
          <>
            <div className="mb-4 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-card md:grid md:grid-cols-[17rem_1fr]">
              {property.images[0] ? <PropertyImage propertyId={property.id} image={property.images[0]} alt={canManage || property.images.length > 1 ? "" : property.title} className="h-44 w-full md:h-full" /> : <PropertyArt property={property} className="h-44 w-full md:h-full" />}
              <div className="p-5">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <h1 className="text-3xl text-navy-900">{displayTitle(property)}</h1>
                    <p className="mt-1 flex items-center gap-1 text-sm text-slate-600">
                      <MapPin aria-hidden className="h-3.5 w-3.5 shrink-0" />
                      {[property.locality, property.city, property.state].filter(Boolean).join(", ")}
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {canManage && (
                      <>
                        <Link to={`/properties/${id}/edit`} className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium shadow-sm hover:bg-slate-50">
                          <Pencil aria-hidden className="h-4 w-4" /> Edit
                        </Link>
                        <Button variant="secondary" onClick={() => setConfirmArchive(true)}>
                          <Trash2 aria-hidden className="h-4 w-4" /> Archive
                        </Button>
                      </>
                    )}
                    {user && !canManage && <ReportControl propertyId={id} />}
                  </div>
                </div>
                <p className="figure mt-3 text-3xl text-navy-900">{property.asking_price ? money(property.asking_price, property.currency) : "Price on request"}</p>
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <StatusBadge status={property.listing_status} />
                  <StatusBadge status={property.verification_status} />
                  {property.is_demo && <SyntheticBadge />}
                </div>
                <div className="mt-4 flex flex-wrap gap-x-5 gap-y-2 text-sm font-medium text-teal-700">
                  <Link to={`/calculator?property=${id}`} className="inline-flex items-center gap-1.5"><Calculator aria-hidden className="h-4 w-4" /> Calculate returns</Link>
                  <Link to={`/properties/${id}/report`} className="inline-flex items-center gap-1.5"><FileText aria-hidden className="h-4 w-4" /> Property report</Link>
                </div>
              </div>
            </div>
            {property.is_demo && <div className="mb-4"><Notice tone="warning">This is a fictional demo record. It does not describe a real property.</Notice></div>}
            <div className="mb-4 space-y-4">
              {canManage && <PropertyJourney insights={insights.data} propertyId={id} />}
              <DecisionSnapshot insights={insights.data} propertyId={id} signedIn={Boolean(user)} />
            </div>

            <div className="grid gap-4 lg:grid-cols-3">
              <div className="space-y-4 lg:col-span-2">
                <ImagesCard property={property} canManage={canManage} onChanged={state.reload} />
                <Card title="Characteristics">
                  <KeyValues
                    items={[
                      ["Type", titleCase(property.property_type)],
                      ...(property.access_level === "full" ? [["Address", `${property.address_line1}, ${property.postal_code}`]] : []),
                      ["Built-up area", area(property.built_up_area_sqft)],
                      ["Land area", area(property.land_area_sqft)],
                      ["Bedrooms", property.bedrooms],
                      ["Bathrooms", property.bathrooms],
                      ["Construction year", property.construction_year],
                      ["Age", property.property_age === null ? null : `${property.property_age} years`],
                      ["Floor", property.floor_number === null ? null : `${property.floor_number} of ${property.total_floors ?? "?"}`],
                      ["Condition", titleCase(property.condition)],
                      ["Parking spaces", property.parking_spaces],
                      ["Amenities", property.amenities.length ? property.amenities.map(titleCase).join(", ") : "None recorded"],
                      ["Asking price", money(property.asking_price, property.currency)],
                      ["Monthly rent", money(property.monthly_rent, property.currency)],
                      ...(property.access_level === "full" ? [["Last sale", property.last_sale_price ? `${money(property.last_sale_price, property.currency)} on ${property.last_sale_date ? date(property.last_sale_date) : "unknown date"}` : "Not recorded"]] : []),
                    ]}
                  />
                  {property.description && <p className="mt-4 whitespace-pre-line text-sm text-slate-700">{property.description}</p>}
                </Card>
                <Card title="Valuation history" action={<ClaimBadge kind="ai" />}>
                  {valuations.data?.length === 1 ? (
                    <p className="text-sm text-slate-600">
                      One estimate so far: <span className="tabular font-medium text-navy-900">{money(latest.predicted_value, latest.currency)}</span> on {date(latest.predicted_at)}. A trend appears here once there is another.
                    </p>
                  ) : (
                    <TrendChart
                      label="Estimated value over time"
                      currency={property.currency}
                      valueHeader="Estimate"
                      points={[...(valuations.data ?? [])].reverse().map((item) => ({ x: item.predicted_at, value: item.predicted_value }))}
                      emptyTitle="No estimates yet"
                      emptyText="Request a valuation to start this history."
                    />
                  )}
                </Card>
                <div id="verification" className="scroll-mt-20">
                  <VerificationCard property={property} canManage={canManage} onChanged={state.reload} />
                </div>
                {(canManage || property.renovations.length > 0) && (
                  <Card title="Renovation history">
                    <DataTable
                      rows={property.renovations}
                      rowKey={(row) => row.id}
                      empty={<Empty title="No renovations recorded" />}
                      columns={[
                        { header: "Completed", cell: (row) => row.completed_on },
                        { header: "Work", cell: (row) => row.description },
                        { header: "Cost", cell: (row) => money(row.cost, property.currency) },
                      ]}
                    />
                    {canManage && <RenovationForm propertyId={property.id} onSaved={state.reload} />}
                  </Card>
                )}
              </div>

              <div className="space-y-4">
                <Card title="Latest estimate" action={<ClaimBadge kind="ai" />}>
                  {latest ? (
                    <>
                      <p className="figure text-3xl">{money(latest.predicted_value, latest.currency)}</p>
                      <p className="mt-1 text-xs text-slate-500">{dateTime(latest.predicted_at)}</p>
                      {latest.trained_on_synthetic_data && <p className="mt-2"><SyntheticBadge /></p>}
                    </>
                  ) : (
                    <p className="text-sm text-slate-600">No estimate has been made yet.</p>
                  )}
                  {user && (
                    <Link to={`/valuations?property=${id}`} className="mt-3 inline-flex items-center gap-2 text-sm font-medium text-teal-700">
                      <Sparkles aria-hidden className="h-4 w-4" /> Open valuation workspace
                    </Link>
                  )}
                </Card>
                <Card title="Digital twin">
                  {twin.data ? (
                    <>
                      <p className="text-sm text-slate-700">Version {twin.data.version}, synced {dateTime(twin.data.last_synced_at)}.</p>
                      <Link to={`/properties/${id}/twin`} className="mt-3 inline-flex items-center gap-2 text-sm font-medium text-teal-700">
                        <Boxes aria-hidden className="h-4 w-4" /> Open twin workspace
                      </Link>
                    </>
                  ) : canManage ? (
                    <Link to={`/properties/${id}/twin`} className="inline-flex items-center gap-2 text-sm font-medium text-teal-700">
                      <Boxes aria-hidden className="h-4 w-4" /> Create a digital twin
                    </Link>
                  ) : (
                    <p className="text-sm text-slate-600">{user ? "No digital twin is available to you for this property." : "Sign in as an investor to explore its twin."}</p>
                  )}
                </Card>
                <Card title="Blockchain record" action={chainRecord.data && <ClaimBadge kind="chain" />}>
                  {chainRecord.data ? (
                    <KeyValues items={[["Version", chainRecord.data.record_version], ["Record hash", shortHash(chainRecord.data.record_hash)], ["Network", chainRecord.data.network]]} />
                  ) : (
                    <p className="text-sm text-slate-600">Not registered on the blockchain.</p>
                  )}
                  {property.access_level === "full" && (
                    <Link to={`/properties/${id}/blockchain`} className="mt-3 inline-flex items-center gap-2 text-sm font-medium text-teal-700">
                      <Blocks aria-hidden className="h-4 w-4" /> Open blockchain verification
                    </Link>
                  )}
                </Card>
              </div>
            </div>

            <ConfirmDialog open={confirmArchive} title="Archive this property?" confirmLabel="Archive" tone="danger" busy={archive.busy} error={archive.error} onCancel={() => setConfirmArchive(false)} onConfirm={() => archive.run()}>
              It will be removed from public listings. Its history is kept.
            </ConfirmDialog>
          </>
        );
      }}
    </Loadable>
  );
}
