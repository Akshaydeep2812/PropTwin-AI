import { Bath, BedDouble, Heart, MapPin, Ruler } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../services/api";
import { area, dateTime, displayTitle, money, titleCase } from "../utils/format";
import { FactorBars } from "./charts";
import { Badge, Card, ClaimBadge, Notice, StatusBadge, SyntheticBadge } from "./ui";

/** Images load through the API client, because a draft's images need the signed-in user's token. */
export function PropertyImage({ propertyId, image, className = "", alt = "Property" }) {
  const [url, setUrl] = useState(null);
  useEffect(() => {
    let current = null;
    let cancelled = false;
    api.properties
      .imageBlob(propertyId, image.id)
      .then((blob) => {
        if (cancelled) return;
        current = URL.createObjectURL(blob);
        setUrl(current);
      })
      .catch(() => setUrl(null));
    return () => {
      cancelled = true;
      if (current) URL.revokeObjectURL(current);
    };
  }, [propertyId, image.id]);
  if (!url) return <div className={`animate-pulse bg-slate-200 ${className}`} aria-hidden />;
  return <img src={url} alt={alt} className={`object-cover ${className}`} />;
}

const ART_TONES = [
  ["#17304f", "#0f2038", "#dcc48f"],
  ["#134e4a", "#0f2038", "#ccfbf1"],
  ["#3b3a5c", "#17304f", "#dcc48f"],
  ["#4a3b2a", "#17304f", "#f5ecd8"],
  ["#1f4e5f", "#0a1628", "#f5ecd8"],
];

function hashOf(text) {
  let hash = 0;
  for (const letter of String(text)) hash = (hash * 31 + letter.charCodeAt(0)) >>> 0;
  return hash;
}

function Windows({ x, y, columns, rows, width, height, seed, light }) {
  const cells = [];
  for (let row = 0; row < rows; row += 1) {
    for (let column = 0; column < columns; column += 1) {
      const lit = (seed + row * 7 + column * 13) % 5 < 2;
      cells.push(<rect key={`${row}-${column}`} x={x + column * width * 1.8} y={y + row * height * 1.7} width={width} height={height} fill={light} opacity={lit ? 0.9 : 0.18} />);
    }
  }
  return <>{cells}</>;
}

/** A drawn stand-in used when a property has no photo. It only depicts the property's type, never the property itself. */
export function PropertyArt({ property, className = "" }) {
  const seed = hashOf(property.id ?? property.title);
  const [from, to, light] = ART_TONES[seed % ART_TONES.length];
  const type = property.property_type;
  const body = "#ffffff";
  const id = `art-${property.id ?? seed}`;
  return (
    <svg aria-hidden viewBox="0 0 320 150" preserveAspectRatio="xMidYMax slice" className={className}>
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor={from} />
          <stop offset="1" stopColor={to} />
        </linearGradient>
      </defs>
      <rect width="320" height="150" fill={`url(#${id})`} />
      <circle cx={40 + (seed % 240)} cy="34" r="16" fill={light} opacity="0.16" />
      <rect x="0" y="134" width="320" height="16" fill={body} opacity="0.1" />
      <g fillOpacity="0.14" fill={body}>
        <rect x={(seed % 40) + 8} y="74" width="36" height="60" />
        <rect x={250 - (seed % 30)} y="60" width="44" height="74" />
      </g>
      {type === "apartment" && (
        <>
          <rect x="118" y="20" width="84" height="114" fill={body} fillOpacity="0.2" />
          <Windows x={127} y={30} columns={4} rows={7} width={9} height={8} seed={seed} light={light} />
        </>
      )}
      {type === "commercial" && (
        <>
          <rect x="88" y="44" width="144" height="90" fill={body} fillOpacity="0.2" />
          <Windows x={98} y={54} columns={7} rows={4} width={10} height={11} seed={seed} light={light} />
          <rect x="146" y="116" width="28" height="18" fill={light} opacity="0.7" />
        </>
      )}
      {type === "house" && (
        <>
          <path d="M104 88 160 46l56 42z" fill={light} opacity="0.75" />
          <rect x="116" y="88" width="88" height="46" fill={body} fillOpacity="0.22" />
          <rect x="150" y="106" width="20" height="28" fill={light} opacity="0.75" />
          <Windows x={124} y={98} columns={1} rows={1} width={16} height={14} seed={1} light={light} />
          <Windows x={180} y={98} columns={1} rows={1} width={16} height={14} seed={1} light={light} />
        </>
      )}
      {type === "villa" && (
        <>
          <rect x="74" y="96" width="172" height="38" fill={body} fillOpacity="0.22" />
          <rect x="100" y="62" width="104" height="34" fill={body} fillOpacity="0.28" />
          <rect x="92" y="58" width="120" height="5" fill={light} opacity="0.8" />
          <rect x="68" y="92" width="184" height="5" fill={light} opacity="0.8" />
          <Windows x={110} y={70} columns={5} rows={1} width={10} height={16} seed={seed} light={light} />
          <Windows x={86} y={106} columns={7} rows={1} width={12} height={18} seed={seed + 3} light={light} />
          <circle cx="270" cy="108" r="17" fill={light} opacity="0.3" />
          <rect x="268" y="108" width="4" height="26" fill={light} opacity="0.4" />
        </>
      )}
      {type === "townhouse" && (
        <>
          {[92, 138, 184].map((x, index) => (
            <g key={x}>
              <path d={`M${x} 72 ${x + 21} 50l21 22z`} fill={light} opacity="0.7" />
              <rect x={x} y="72" width="42" height="62" fill={body} fillOpacity={0.18 + index * 0.05} />
              <rect x={x + 15} y="110" width="12" height="24" fill={light} opacity="0.75" />
              <Windows x={x + 8} y={82} columns={2} rows={1} width={9} height={12} seed={seed + index} light={light} />
            </g>
          ))}
        </>
      )}
      {type === "plot" && (
        <>
          <path d="M60 134 110 94h100l50 40z" fill={light} opacity="0.25" stroke={light} strokeOpacity="0.8" strokeDasharray="5 4" />
          <circle cx="160" cy="76" r="9" fill={light} opacity="0.85" />
          <path d="M153 81 160 106l7-25z" fill={light} opacity="0.85" />
        </>
      )}
    </svg>
  );
}

const pricePerSqft = (property) => (property.asking_price && property.built_up_area_sqft ? Number(property.asking_price) / Number(property.built_up_area_sqft) : null);
const grossYield = (property) => (property.monthly_rent && property.asking_price ? (Number(property.monthly_rent) * 1200) / Number(property.asking_price) : null);

export function PropertyCard({ property, saved, onToggleSaved, selected, onToggleSelected }) {
  const cover = property.images?.[0];
  const perSqft = pricePerSqft(property);
  const yieldPct = grossYield(property);
  return (
    <article className="group flex flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-card transition-shadow hover:shadow-lift">
      <Link to={`/properties/${property.id}`} className="relative block" tabIndex={-1} aria-hidden>
        {cover ? <PropertyImage propertyId={property.id} image={cover} className="h-40 w-full" alt="" /> : <PropertyArt property={property} className="h-40 w-full" />}
        <span className="absolute left-3 top-3 rounded-full bg-white/90 px-2.5 py-0.5 text-xs font-medium text-navy-900 backdrop-blur">{titleCase(property.property_type)}</span>
      </Link>
      <div className="flex flex-1 flex-col gap-2 p-4">
        <div className="flex flex-wrap gap-1.5">
          <StatusBadge status={property.verification_status} />
          {property.is_demo && <SyntheticBadge />}
        </div>
        <Link to={`/properties/${property.id}`} className="font-semibold leading-snug text-navy-900 hover:text-teal-700">
          {displayTitle(property)}
        </Link>
        <p className="flex items-center gap-1 text-sm text-slate-600">
          <MapPin aria-hidden className="h-3.5 w-3.5 shrink-0" />
          {[property.locality, property.city].filter(Boolean).join(", ")}
        </p>
        <p className="figure text-xl text-navy-900">{property.asking_price ? money(property.asking_price, property.currency) : "Price on request"}</p>
        {(perSqft !== null || yieldPct !== null) && (
          <p className="tabular text-xs text-slate-600">
            {perSqft !== null && `${money(perSqft, property.currency)} per sq ft`}
            {perSqft !== null && yieldPct !== null && " · "}
            {yieldPct !== null && `${yieldPct.toFixed(1)}% gross yield`}
          </p>
        )}
        <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-600">
          {property.built_up_area_sqft && (
            <li className="flex items-center gap-1">
              <Ruler aria-hidden className="h-3.5 w-3.5" />
              {area(property.built_up_area_sqft)}
            </li>
          )}
          {property.bedrooms !== null && (
            <li className="flex items-center gap-1">
              <BedDouble aria-hidden className="h-3.5 w-3.5" />
              {property.bedrooms} bed
            </li>
          )}
          {property.bathrooms !== null && (
            <li className="flex items-center gap-1">
              <Bath aria-hidden className="h-3.5 w-3.5" />
              {property.bathrooms} bath
            </li>
          )}
        </ul>
        <div className="mt-auto flex items-center justify-between border-t border-slate-100 pt-3">
          {onToggleSelected ? (
            <label className="flex cursor-pointer items-center gap-2 text-xs font-medium text-slate-600">
              <input type="checkbox" checked={selected} onChange={() => onToggleSelected(property.id)} className="accent-teal-700" />
              Compare
            </label>
          ) : (
            <span />
          )}
          {onToggleSaved && (
            <button type="button" aria-pressed={saved} aria-label={saved ? "Remove from favorites" : "Save to favorites"} onClick={() => onToggleSaved(property.id)} className={saved ? "text-teal-700" : "text-slate-400 hover:text-teal-700"}>
              <Heart aria-hidden className={`h-5 w-5 ${saved ? "fill-current" : ""}`} />
            </button>
          )}
        </div>
      </div>
    </article>
  );
}

export function ValuationResult({ valuation }) {
  const { interval, historical_comparison: comparison, currency } = valuation;
  return (
    <div className="space-y-4">
      <Card>
        <div className="flex flex-wrap items-center gap-2">
          <ClaimBadge kind="ai" />
          {valuation.trained_on_synthetic_data && <SyntheticBadge />}
        </div>
        <p className="mt-3 text-sm text-slate-600">Estimated market value</p>
        <p data-testid="predicted-value" className="figure mt-1 text-5xl text-navy-900">
          {money(valuation.predicted_value, currency)}
        </p>
        {interval && (
          <p className="tabular mt-1 text-sm text-slate-600">
            {Math.round(Number(interval.nominal_coverage) * 100)}% range: {money(interval.lower, currency)} to {money(interval.upper, currency)}
          </p>
        )}
        <p className="mt-3 text-xs text-slate-500">
          Model {valuation.model_version}, {dateTime(valuation.predicted_at)}
        </p>
        <p className="mt-3 rounded-md bg-slate-50 p-3 text-sm text-slate-700">{valuation.disclaimer}</p>
      </Card>

      <Card title="What moved this estimate">
        <FactorBars factors={valuation.factors} currency={currency} />
        <p className="mt-2 text-xs text-slate-500">Each bar shows how much the model's estimate changes when that input is moved to a typical value. This describes the model, not what causes prices in the market.</p>
      </Card>

      {(comparison.previous_value || comparison.last_sale_price) && (
        <Card title="Historical comparison">
          <ul className="space-y-2 text-sm">
            {comparison.previous_value && (
              <li>
                Previous estimate: <span className="tabular font-medium">{money(comparison.previous_value, currency)}</span> on {dateTime(comparison.previous_valued_at)}
                {comparison.change_from_previous_pct && <span className="tabular"> ({comparison.change_from_previous_pct}% change)</span>}
              </li>
            )}
            {comparison.last_sale_price && (
              <li>
                Last recorded sale: <span className="tabular font-medium">{money(comparison.last_sale_price, currency)}</span> on {comparison.last_sale_date}
              </li>
            )}
          </ul>
        </Card>
      )}

      <Notice tone="warning">
        <p className="font-medium">Limitations of this estimate</p>
        <ul className="mt-1 list-inside list-disc space-y-1">
          {valuation.limitations.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      </Notice>
    </div>
  );
}

export function ModelBadge({ model }) {
  if (!model) return null;
  if (!model.available) return <Badge tone="red">No active model</Badge>;
  return <Badge tone="teal">Model {model.version}</Badge>;
}

export const PROPERTY_TYPES = ["apartment", "house", "villa", "townhouse", "plot", "commercial"].map((value) => ({ value, label: titleCase(value) }));
export const CONDITIONS = ["poor", "fair", "good", "very_good", "excellent"].map((value) => ({ value, label: titleCase(value) }));
