import { AlertCircle, Bot, CheckCircle2, ChevronLeft, ChevronRight, Dices, FileCheck2, Link2, Loader2, X } from "lucide-react";
import { useEffect, useId, useRef } from "react";

const BUTTON_STYLES = {
  primary: "bg-teal-700 text-white shadow-sm hover:bg-teal-600 disabled:bg-slate-300 disabled:shadow-none",
  secondary: "bg-white text-navy-900 border border-slate-300 shadow-sm hover:border-slate-400 hover:bg-slate-50 disabled:text-slate-400",
  danger: "bg-red-700 text-white hover:bg-red-600 disabled:bg-slate-300",
  ghost: "text-navy-800 hover:bg-slate-100 disabled:text-slate-400",
};

export function Button({ variant = "primary", busy = false, children, className = "", disabled, type = "button", ...props }) {
  return (
    <button
      type={type}
      disabled={disabled || busy}
      className={`inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors disabled:cursor-not-allowed ${BUTTON_STYLES[variant]} ${className}`}
      {...props}
    >
      {busy && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}
      {children}
    </button>
  );
}

export function Card({ title, action, children, className = "" }) {
  return (
    <section className={`rounded-xl border border-slate-200 bg-white p-5 shadow-card ${className}`}>
      {(title || action) && (
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
          {title && <h2 className="text-base font-semibold text-navy-900">{title}</h2>}
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

export function PageHeader({ title, subtitle, action }) {
  return (
    <header className="mb-6 flex flex-wrap items-start justify-between gap-3">
      <div>
        <h1 className="text-3xl text-navy-900">{title}</h1>
        {subtitle && <p className="mt-1 max-w-3xl text-sm text-slate-600">{subtitle}</p>}
      </div>
      {action}
    </header>
  );
}

export function Stat({ label, value, hint, icon: Icon, badge }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-card">
      <div className="flex items-start justify-between gap-2">
        <p className="text-xs font-medium text-slate-600">{label}</p>
        {Icon && <Icon aria-hidden className="h-4 w-4 shrink-0 text-brass-600" />}
      </div>
      <p className="figure mt-1.5 text-2xl text-navy-900">{value}</p>
      {hint && <p className="mt-1 text-xs text-slate-500">{hint}</p>}
      {badge && <div className="mt-2">{badge}</div>}
    </div>
  );
}

export function Spinner({ label = "Loading" }) {
  return (
    <div role="status" className="flex items-center justify-center gap-2 py-10 text-sm text-slate-500">
      <Loader2 aria-hidden className="h-5 w-5 animate-spin text-teal-700" />
      {label}…
    </div>
  );
}

export function ErrorNote({ error, onRetry }) {
  if (!error) return null;
  const message = typeof error === "string" ? error : error.message;
  return (
    <div role="alert" className="flex items-start gap-2 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800">
      <AlertCircle aria-hidden className="mt-0.5 h-4 w-4 shrink-0" />
      <div className="flex-1">
        <p>{message}</p>
        {error.fields?.length > 0 && (
          <ul className="mt-1 list-inside list-disc">
            {error.fields.map((field) => (
              <li key={`${field.field}-${field.message}`}>
                {field.field}: {field.message}
              </li>
            ))}
          </ul>
        )}
        {onRetry && (
          <button type="button" onClick={onRetry} className="mt-1 font-medium underline">
            Try again
          </button>
        )}
      </div>
    </div>
  );
}

export function Notice({ tone = "info", children }) {
  const tones = {
    info: "border-slate-200 bg-slate-50 text-slate-700",
    warning: "border-amber-300 bg-amber-50 text-amber-900",
    success: "border-teal-100 bg-teal-50 text-teal-700",
  };
  return <div className={`rounded-md border p-3 text-sm ${tones[tone]}`}>{children}</div>;
}

export function Empty({ title, children, action }) {
  return (
    <div className="rounded-xl border border-dashed border-slate-300 bg-white/60 px-4 py-10 text-center">
      <p className="font-medium text-navy-900">{title}</p>
      {children && <p className="mx-auto mt-1 max-w-md text-sm text-slate-600">{children}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

/** Loading, error and data states in one place, so that no page can show a blank screen. */
export function Loadable({ state, children, label }) {
  if (state.loading && !state.data) return <Spinner label={label} />;
  if (state.error) return <ErrorNote error={state.error} onRetry={state.reload} />;
  if (!state.data) return null;
  return children(state.data);
}

const inputClass = "w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-navy-900 transition-colors placeholder:text-slate-400 hover:border-slate-400 aria-[invalid=true]:border-red-500";

export function Field({ label, error, hint, children }) {
  const id = useId();
  const errorId = `${id}-error`;
  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-sm font-medium text-navy-800">
        {label}
      </label>
      {children({ id, "aria-invalid": Boolean(error), "aria-describedby": error ? errorId : undefined, className: inputClass })}
      {hint && !error && <p className="mt-1 text-xs text-slate-500">{hint}</p>}
      {error && (
        <p id={errorId} className="mt-1 text-xs text-red-700">
          {error}
        </p>
      )}
    </div>
  );
}

export function TextField({ label, error, hint, registration, ...props }) {
  return <Field label={label} error={error} hint={hint}>{(field) => <input {...field} {...props} {...registration} />}</Field>;
}

export function SelectField({ label, error, hint, registration, options, ...props }) {
  return (
    <Field label={label} error={error} hint={hint}>
      {(field) => (
        <select {...field} {...props} {...registration}>
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      )}
    </Field>
  );
}

export function TextAreaField({ label, error, hint, registration, ...props }) {
  return <Field label={label} error={error} hint={hint}>{(field) => <textarea rows={3} {...field} {...props} {...registration} />}</Field>;
}

export function Badge({ children, tone = "slate" }) {
  const tones = {
    slate: "bg-slate-100 text-slate-700",
    teal: "bg-teal-100 text-teal-700",
    amber: "bg-amber-100 text-amber-900",
    red: "bg-red-100 text-red-800",
    navy: "bg-navy-800 text-white",
    indigo: "bg-indigo-100 text-indigo-800",
  };
  return <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${tones[tone]}`}>{children}</span>;
}

const CLAIMS = {
  ai: { icon: Bot, tone: "teal", label: "AI estimate" },
  hypothetical: { icon: Dices, tone: "amber", label: "Hypothetical simulation" },
  document: { icon: FileCheck2, tone: "indigo", label: "Verifier decision" },
  chain: { icon: Link2, tone: "navy", label: "Blockchain-confirmed" },
};

/** The four kinds of claim look different everywhere, so that one is never mistaken for another. */
export function ClaimBadge({ kind }) {
  const { icon: Icon, tone, label } = CLAIMS[kind];
  return (
    <Badge tone={tone}>
      <Icon aria-hidden className="h-3 w-3" />
      {label}
    </Badge>
  );
}

export function SyntheticBadge() {
  return <Badge tone="amber">Synthetic demo data</Badge>;
}

const STATUS_TONES = {
  confirmed: "teal", verified: "teal", approved: "teal", accepted: "teal", active: "teal", listed: "teal", match: "teal", succeeded: "teal",
  pending: "amber", submitted: "amber", requested: "amber", proposed: "amber", candidate: "amber", under_offer: "amber", queued: "amber", running: "amber",
  failed: "red", reverted: "red", rejected: "red", mismatch: "red", dead: "red", archived: "slate",
};

export function StatusBadge({ status }) {
  return <Badge tone={STATUS_TONES[status] ?? "slate"}>{(status ?? "unknown").replace(/_/g, " ")}</Badge>;
}

export function Pagination({ page, pageSize, total, onChange }) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (pages <= 1) return null;
  return (
    <nav aria-label="Pagination" className="mt-4 flex items-center justify-between text-sm text-slate-600">
      <span>
        Page {page} of {pages} ({total} results)
      </span>
      <div className="flex gap-2">
        <Button variant="secondary" disabled={page <= 1} onClick={() => onChange(page - 1)} aria-label="Previous page">
          <ChevronLeft aria-hidden className="h-4 w-4" />
        </Button>
        <Button variant="secondary" disabled={page >= pages} onClick={() => onChange(page + 1)} aria-label="Next page">
          <ChevronRight aria-hidden className="h-4 w-4" />
        </Button>
      </div>
    </nav>
  );
}

export function ConfirmDialog({ open, title, children, confirmLabel = "Confirm", tone = "primary", busy, error, onConfirm, onCancel }) {
  const dialog = useRef(null);
  useEffect(() => {
    if (open) dialog.current?.focus();
  }, [open]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-navy-950/50 p-4">
      <div
        ref={dialog}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onKeyDown={(event) => event.key === "Escape" && !busy && onCancel()}
        className="w-full max-w-md rounded-xl bg-white p-5 shadow-xl"
      >
        <div className="flex items-start justify-between gap-3">
          <h2 className="text-lg font-semibold text-navy-900">{title}</h2>
          <button type="button" aria-label="Close" onClick={onCancel} disabled={busy} className="text-slate-500 hover:text-navy-900">
            <X aria-hidden className="h-5 w-5" />
          </button>
        </div>
        <div className="mt-2 text-sm text-slate-700">{children}</div>
        {error && (
          <div className="mt-3">
            <ErrorNote error={error} />
          </div>
        )}
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="secondary" onClick={onCancel} disabled={busy}>
            Cancel
          </Button>
          <Button variant={tone} busy={busy} onClick={onConfirm}>
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}

export function SuccessNote({ children }) {
  return (
    <div role="status" className="flex items-start gap-2 rounded-md border border-teal-100 bg-teal-50 p-3 text-sm text-teal-700">
      <CheckCircle2 aria-hidden className="mt-0.5 h-4 w-4 shrink-0" />
      <div>{children}</div>
    </div>
  );
}

export function KeyValues({ items }) {
  return (
    <dl className="grid grid-cols-1 gap-x-6 gap-y-3 sm:grid-cols-2">
      {items.map(([label, value]) => (
        <div key={label}>
          <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</dt>
          <dd className="mt-0.5 break-words text-sm text-navy-900">{value ?? "Not available"}</dd>
        </div>
      ))}
    </dl>
  );
}

export function DataTable({ columns, rows, rowKey, empty }) {
  if (!rows.length) return empty ?? <Empty title="Nothing here yet" />;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
            {columns.map((column) => (
              <th key={column.header} scope="col" className="py-2 pr-4 font-medium">
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={rowKey(row)} className="border-b border-slate-100 last:border-0">
              {columns.map((column) => (
                <td key={column.header} className="py-2.5 pr-4 align-top text-navy-900">
                  {column.cell(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
