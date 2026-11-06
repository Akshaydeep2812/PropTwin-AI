import { CheckCircle2, ShieldAlert, Wallet } from "lucide-react";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useParams } from "react-router-dom";
import { PageGuide } from "../components/guide";
import { Button, Card, ClaimBadge, ConfirmDialog, DataTable, Empty, ErrorNote, KeyValues, Loadable, Notice, PageHeader, StatusBadge, TextField } from "../components/ui";
import { useAction, useAsync } from "../hooks/useAsync";
import { useAuth } from "../hooks/useAuth";
import { api } from "../services/api";
import { sendPreparedCall, walletAvailable } from "../services/wallet";
import { dateTime, shortHash, titleCase } from "../utils/format";

const OPEN = ["pending", "submitted"];
const POLL_MS = 2500;

/** Watches a transaction until the server reports it settled. This page never decides that a transaction succeeded. */
function useTransactionWatch(initial, onSettled) {
  const [transaction, setTransaction] = useState(initial);
  useEffect(() => setTransaction(initial), [initial]);
  const id = transaction?.id;
  const open = transaction?.status === "submitted";
  useEffect(() => {
    if (!id || !open) return undefined;
    const timer = setInterval(async () => {
      try {
        const latest = await api.chain.transaction(id);
        setTransaction(latest);
        if (latest.status !== "submitted") onSettled?.(latest);
      } catch {
        // A failed poll changes nothing. The next tick tries again and the worker keeps reconciling.
      }
    }, POLL_MS);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, open]);
  return transaction;
}

function TransactionStatus({ transaction }) {
  if (!transaction) return null;
  if (transaction.status === "confirmed") {
    return (
      <Notice tone="success">
        <div className="flex flex-wrap items-center gap-2">
          <ClaimBadge kind="chain" />
          Confirmed in block {transaction.block_number} ({transaction.confirmations} of {transaction.required_confirmations} required confirmations).
        </div>
      </Notice>
    );
  }
  if (OPEN.includes(transaction.status)) {
    return <Notice tone="warning">Transaction {transaction.status}. It is not confirmed yet ({transaction.confirmations} of {transaction.required_confirmations} confirmations).</Notice>;
  }
  return <ErrorNote error={`Transaction ${transaction.status}: ${transaction.failure_reason ?? "no reason recorded"}`} />;
}

function IntegrityResult({ result }) {
  const matched = result.result === "match";
  return (
    <div data-testid="integrity-result" data-result={result.result} className={`rounded-md border p-4 ${matched ? "border-teal-100 bg-teal-50" : "border-amber-300 bg-amber-50"}`}>
      <div className="flex items-center gap-2 font-semibold text-navy-900">
        {matched ? <CheckCircle2 aria-hidden className="h-5 w-5 text-teal-700" /> : <ShieldAlert aria-hidden className="h-5 w-5 text-amber-700" />}
        {matched ? "Record matches the blockchain" : titleCase(result.result)}
      </div>
      <p className="mt-1 text-sm text-slate-700">{result.detail}</p>
      {result.changed_fields?.length > 0 && <p className="mt-1 text-sm text-slate-700">Fields that differ: {result.changed_fields.map(titleCase).join(", ")}.</p>}
      {result.recalculated_hash && (
        <dl className="mt-3 space-y-1 text-xs">
          <div><dt className="inline font-medium">Recalculated: </dt><dd className="inline break-all font-mono">{result.recalculated_hash}</dd></div>
          {result.on_chain_hash && <div><dt className="inline font-medium">On-chain: </dt><dd className="inline break-all font-mono">{result.on_chain_hash}</dd></div>}
        </dl>
      )}
      <p className="mt-3 text-xs text-slate-600">Checked {dateTime(result.checked_at)}.</p>
    </div>
  );
}

export function BlockchainPage() {
  const { id } = useParams();
  const { user } = useAuth();
  const property = useAsync(() => api.properties.get(id), [id]);
  const history = useAsync(() => api.chain.history(id), [id]);
  const network = useAsync(() => api.chain.network(), []);
  const [verification, setVerification] = useState(null);
  const [confirming, setConfirming] = useState(false);
  const [submitted, setSubmitted] = useState(null);
  const watched = useTransactionWatch(submitted, () => history.reload());
  const verify = useAction(async () => setVerification(await api.chain.verify(id)));
  const register = useAction(async () => {
    setSubmitted(await api.chain.register(id));
    setConfirming(false);
    setVerification(null);
    history.reload();
  });
  const handOver = useAction(async () => {
    setSubmitted(await api.chain.assignController(id));
    history.reload();
  });

  const latestValuation = useAsync(() => api.properties.valuations(id, { page_size: 1 }), [id]);
  const commitEstimate = useAction(async (valuationId) => {
    setSubmitted(await api.chain.commitValuation(valuationId));
    history.reload();
  });

  const canManage = property.data && (property.data.owner_id === user?.id || user?.roles.includes("admin"));
  const record = history.data?.record;
  const registered = record && record.record_version > 0;
  const custodial = registered && user?.wallet_address && record.controller_address !== user.wallet_address;

  return (
    <>
      <PageHeader title="Blockchain verification" subtitle={property.data && <Link className="text-teal-700 underline" to={`/properties/${id}`}>{property.data.title}</Link>} />
      <PageGuide
        id="blockchain"
        steps={["Commit the record. The app stores a salted hash on the network, never the address or the documents.", "Change the property later if you need to. Each commit adds a new version, and earlier ones are kept.", "Run an integrity check at any time. A mismatch names the fields that changed since the last commit."]}
        note="A matching hash shows the record has not changed since it was committed. It does not show who legally owns the property, or that the data was true to begin with."
      />
      <div className="mb-4">
        <Notice>{history.data?.legal_note ?? "A blockchain record is a tamper-evident commitment. It does not establish legal ownership or prove that the underlying documents are authentic."}</Notice>
      </div>
      {network.data && !network.data.reachable && (
        <div className="mb-4">
          <Notice tone="warning">The blockchain network is not available: {network.data.detail ?? "the node could not be reached"}. Existing records can be viewed, but new transactions will fail.</Notice>
        </div>
      )}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="On-chain record" action={registered && <ClaimBadge kind="chain" />}>
          <Loadable state={history} label="Loading record">
            {() =>
              registered ? (
                <KeyValues
                  items={[
                    ["Record identifier", <span className="break-all font-mono text-xs" key="key">{record.property_key}</span>],
                    ["Record hash", <span className="break-all font-mono text-xs" key="hash">{record.record_hash}</span>],
                    ["Record version", record.record_version],
                    ["Network", record.network],
                    ["Contract address", <span className="break-all font-mono text-xs" key="contract">{record.contract_address}</span>],
                    ["Controlling address", <span className="break-all font-mono text-xs" key="controller">{record.controller_address}</span>],
                  ]}
                />
              ) : (
                <Empty title="Not registered yet">Registering commits a salted hash of this record. No address or personal data goes on-chain.</Empty>
              )
            }
          </Loadable>
          {registered && <p className="mt-3 text-xs text-slate-500">The controlling address manages this record on-chain. Controlling a wallet is not legal ownership of the property.</p>}
          {canManage && (
            <div className="mt-4 flex flex-wrap gap-2">
              <Button onClick={() => setConfirming(true)}>{registered ? "Commit current version" : "Register on blockchain"}</Button>
              {custodial && (
                <Button variant="secondary" busy={handOver.busy} onClick={() => handOver.run()}>
                  Move control to my wallet
                </Button>
              )}
              {registered && latestValuation.data?.[0] && (
                <Button variant="secondary" busy={commitEstimate.busy} onClick={() => commitEstimate.run(latestValuation.data[0].id)}>
                  Commit latest estimate
                </Button>
              )}
            </div>
          )}
          <div className="mt-3 space-y-2">
            <TransactionStatus transaction={watched} />
            <ErrorNote error={handOver.error || commitEstimate.error} />
          </div>
        </Card>
        <Card title="Record integrity">
          <p className="mb-3 text-sm text-slate-600">Recalculates the hash from the current record and compares it with the contract. This detects any change to a covered field since the last commit.</p>
          <Button variant="secondary" busy={verify.busy} onClick={() => verify.run()}>
            Check record integrity
          </Button>
          <div className="mt-3 space-y-3">
            <ErrorNote error={verify.error} />
            {verification && <IntegrityResult result={verification} />}
            {verification && (
              <details className="text-xs text-slate-600">
                <summary className="cursor-pointer font-medium">Fields covered by the hash (version {verification.hash_version})</summary>
                <p className="mt-1">{verification.covered_fields.map(titleCase).join(", ")}</p>
              </details>
            )}
          </div>
        </Card>
      </div>

      <Card title="Transaction and event history" className="mt-4">
        <Loadable state={history} label="Loading history">
          {(data) => (
            <DataTable
              rows={data.transactions}
              rowKey={(row) => row.id}
              empty={<Empty title="No transactions yet" />}
              columns={[
                { header: "Operation", cell: (row) => titleCase(row.operation) },
                { header: "Status", cell: (row) => <StatusBadge status={row.status} /> },
                { header: "Transaction", cell: (row) => <span className="font-mono text-xs" title={row.tx_hash ?? undefined}>{shortHash(row.tx_hash)}</span> },
                { header: "Block", cell: (row) => row.block_number ?? "Pending" },
                { header: "Events", cell: (row) => row.events.map((event) => event.event_name).join(", ") || "None" },
                { header: "Created", cell: (row) => dateTime(row.created_at) },
              ]}
            />
          )}
        </Loadable>
      </Card>

      <ConfirmDialog open={confirming} title={registered ? "Commit this version?" : "Register on the blockchain?"} confirmLabel="Submit transaction" busy={register.busy} error={register.error} onCancel={() => setConfirming(false)} onConfirm={() => register.run()}>
        A transaction with a salted hash of this record will be sent. On-chain data cannot be removed later. It does not establish legal ownership.
      </ConfirmDialog>
    </>
  );
}

function WalletStep({ label, prepare, onDone }) {
  const [phase, setPhase] = useState(null);
  const [preparedId, setPreparedId] = useState(null);
  const action = useAction(async () => {
    if (!walletAvailable()) throw new Error("No browser wallet was found. Install one, such as MetaMask, to sign this transaction.");
    setPhase("Preparing the transaction");
    const { call } = await prepare();
    setPreparedId(call.transaction_id);
    setPhase("Waiting for your wallet");
    try {
      const txHash = await sendPreparedCall(call);
      setPhase("Checking the transaction");
      await api.chain.submit(call.transaction_id, txHash);
      setPreparedId(null);
      setPhase("Waiting for confirmation");
      for (let attempt = 0; attempt < 60; attempt += 1) {
        const latest = await api.chain.transaction(call.transaction_id);
        if (!OPEN.includes(latest.status)) {
          if (latest.status !== "confirmed") throw new Error(`The transaction ${latest.status}: ${latest.failure_reason ?? "no reason recorded"}`);
          break;
        }
        await new Promise((resolve) => setTimeout(resolve, POLL_MS));
      }
      onDone();
    } catch (error) {
      setPhase(null);
      // If the wallet was closed without sending, free the property for its next transaction.
      if (error.code === 4001) await api.chain.abandon(call.transaction_id).catch(() => {});
      throw error;
    } finally {
      setPhase(null);
    }
  });
  return (
    <div className="space-y-2">
      <Button busy={action.busy} onClick={() => action.run()}>
        <Wallet aria-hidden className="h-4 w-4" /> {action.busy && phase ? phase : label}
      </Button>
      <ErrorNote error={action.error} />
      {preparedId && !action.busy && (
        <p className="text-xs text-slate-600">
          A prepared transaction was not completed.{" "}
          <button type="button" className="underline" onClick={() => api.chain.abandon(preparedId).then(() => setPreparedId(null)).catch(() => {})}>
            Discard it
          </button>
        </p>
      )}
    </div>
  );
}

const STEP_TEXT = {
  requested: "Requested. The current owner must propose this on-chain from their wallet.",
  proposed: "Proposed on-chain. Control does not move until the recipient accepts from their wallet.",
  accepted: "Accepted and confirmed on-chain.",
  cancelled: "Cancelled.",
  failed: "Failed.",
};

export function TransfersPage() {
  const { user, hasRole } = useAuth();
  const transfers = useAsync(() => api.chain.transfers(), []);
  const owned = useAsync(() => (hasRole("owner", "admin") ? api.properties.mine({ page_size: 100 }).then((page) => page.items) : Promise.resolve([])), []);
  const saved = useAsync(() => (hasRole("investor") ? api.favorites.list() : Promise.resolve([])), []);
  const [confirming, setConfirming] = useState(null);
  const { register, handleSubmit, reset } = useForm({ defaultValues: { property_id: "", recipient_email: "" } });
  const create = useAction(async (values) => {
    await api.chain.createTransfer({ property_id: confirming?.property_id ?? values.property_id, recipient_email: (confirming?.recipient_email ?? values.recipient_email) || null });
    setConfirming(null);
    reset();
    transfers.reload();
  });
  const cancelRequest = useAction(async (id) => {
    await api.chain.cancelTransfer(id);
    transfers.reload();
  });
  const isOwner = hasRole("owner", "admin");
  const propertyOptions = isOwner ? owned.data ?? [] : saved.data ?? [];
  const titles = Object.fromEntries([...(owned.data ?? []), ...(saved.data ?? [])].map((item) => [item.id, item.title]));

  return (
    <>
      <PageHeader title="Ownership transfers" subtitle="A two-step process: the current controller proposes, and the recipient accepts. Both steps are signed in each person's own wallet." />
      <PageGuide
        id="transfers"
        steps={["Link a browser wallet from your profile. Both people need one.", "The current controller creates a transfer and signs the proposal.", "The recipient opens it here and signs the acceptance. Until then, the controller can cancel, and the recipient can decline by not accepting."]}
        note="This moves control of the on-chain record in this app. It is not a legal transfer of property."
      />
      <div className="mb-4">
        <Notice tone="warning">A transfer moves control of the on-chain record and the record in this application. It does not transfer legal title to the property, which requires your jurisdiction's legal process.</Notice>
      </div>
      {!user?.wallet_address && (
        <div className="mb-4">
          <Notice>You have not linked a wallet. <Link className="underline" to="/profile">Link one in your profile</Link> before taking part in a transfer.</Notice>
        </div>
      )}
      <div className="grid gap-4 lg:grid-cols-3">
        <Card title={isOwner ? "Start a transfer" : "Request a transfer"}>
          <form onSubmit={handleSubmit((values) => setConfirming(values))} className="space-y-3">
            <div>
              <label htmlFor="transfer-property" className="text-sm font-medium text-navy-800">
                Property
              </label>
              <select id="transfer-property" {...register("property_id", { required: true })} className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm">
                <option value="">Select a property</option>
                {propertyOptions.map((property) => (
                  <option key={property.id} value={property.id}>
                    {property.title}
                  </option>
                ))}
              </select>
              {!isOwner && <p className="mt-1 text-xs text-slate-500">Listings you have saved to favorites appear here.</p>}
            </div>
            {isOwner && <TextField label="Recipient's account email" type="email" registration={register("recipient_email", { required: true })} />}
            <Button type="submit">{isOwner ? "Create transfer" : "Request transfer"}</Button>
          </form>
        </Card>
        <Card title="Your transfers" className="lg:col-span-2">
          <ErrorNote error={cancelRequest.error} />
          <Loadable state={transfers} label="Loading transfers">
            {(rows) =>
              rows.length === 0 ? (
                <Empty title="No transfers yet" />
              ) : (
                <ul className="space-y-3">
                  {rows.map((transfer) => (
                    <li key={transfer.id} className="rounded-md border border-slate-200 p-4">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <Link to={`/properties/${transfer.property_id}`} className="font-medium text-teal-700 underline">
                          {titles[transfer.property_id] ?? "Property"}
                        </Link>
                        <StatusBadge status={transfer.status} />
                      </div>
                      <p className="mt-1 text-sm text-slate-600">{STEP_TEXT[transfer.status]}</p>
                      <p className="mt-1 break-all font-mono text-xs text-slate-500">To {transfer.to_address}</p>
                      <div className="mt-3">
                        {transfer.status === "requested" && transfer.from_user_id === user.id && <WalletStep label="Propose from my wallet" prepare={() => api.chain.proposeTransfer(transfer.id)} onDone={transfers.reload} />}
                        {transfer.status === "proposed" && transfer.to_user_id === user.id && <WalletStep label="Accept from my wallet" prepare={() => api.chain.acceptTransfer(transfer.id)} onDone={transfers.reload} />}
                        {transfer.status === "proposed" && transfer.from_user_id === user.id && <WalletStep label="Cancel from my wallet" prepare={() => api.chain.cancelTransfer(transfer.id)} onDone={transfers.reload} />}
                        {transfer.status === "requested" && (
                          <Button variant="ghost" className="mt-2" onClick={() => cancelRequest.run(transfer.id)} busy={cancelRequest.busy}>
                            Cancel request
                          </Button>
                        )}
                      </div>
                    </li>
                  ))}
                </ul>
              )
            }
          </Loadable>
        </Card>
      </div>
      <ConfirmDialog open={Boolean(confirming)} title="Start this transfer?" confirmLabel="Continue" busy={create.busy} error={create.error} onCancel={() => setConfirming(null)} onConfirm={() => create.run(confirming)}>
        This does not transfer legal title. Nothing changes until the transfer is signed and confirmed on-chain.
      </ConfirmDialog>
    </>
  );
}
