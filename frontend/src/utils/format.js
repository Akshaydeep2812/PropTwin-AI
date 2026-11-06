const DATE = new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric" });
const DATE_TIME = new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });

/** Money arrives as a decimal string. It is displayed as-is, and never used in arithmetic here. */
export function money(value, currency = "INR") {
  if (value === null || value === undefined || value === "") return "Not available";
  return new Intl.NumberFormat("en-IN", { style: "currency", currency, maximumFractionDigits: 0 }).format(value);
}

export function compactMoney(value, currency = "INR") {
  if (value === null || value === undefined) return "";
  return new Intl.NumberFormat("en-IN", { style: "currency", currency, notation: "compact", maximumFractionDigits: 2 }).format(Number(value));
}

export function percent(value, digits = 2) {
  if (value === null || value === undefined) return "Not available";
  const number = Number(value);
  return `${number > 0 ? "+" : ""}${number.toFixed(digits)}%`;
}

export function plainPercent(value, digits = 2) {
  return value === null || value === undefined ? "Not available" : `${Number(value).toFixed(digits)}%`;
}

export function date(value) {
  return value ? DATE.format(new Date(value)) : "Not available";
}

export function dateTime(value) {
  return value ? DATE_TIME.format(new Date(value)) : "Not available";
}

export function area(value) {
  return value === null || value === undefined ? "Not available" : `${Number(value).toLocaleString("en-IN")} sq ft`;
}

export function titleCase(value) {
  if (!value) return "Not available";
  return value.replace(/_/g, " ").replace(/^\w/, (letter) => letter.toUpperCase());
}

export function shortHash(value) {
  return value ? `${value.slice(0, 10)}…${value.slice(-8)}` : "Not available";
}

/** The seed script marks demo titles in the database. Where a page already shows the demo badge, the prefix only adds noise. */
export function displayTitle(property) {
  return property.is_demo ? property.title.replace(/^\[DEMO\]\s*/, "") : property.title;
}

export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
