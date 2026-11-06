import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, LabelList, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { compactMoney, date as formatDate, money } from "../utils/format";
import { DataTable, Empty } from "./ui";

// Validated with the dataviz palette checker on the white card surface: all colorblind and contrast checks pass.
export const SERIES = { teal: "#0d9488", navy: "#3a4f9c" };
const GRID = "#ece8df";
const AXIS = "#64748b";

/** Keeps a flat or single-point series from drawing an axis whose ticks all round to the same label. */
export function paddedDomain(values) {
  const min = Math.min(...values);
  const max = Math.max(...values);
  const pad = Math.max((max - min) * 0.1, Math.abs(max) * 0.05);
  return [Math.floor(min - pad), Math.ceil(max + pad)];
}

/** Evenly spaced round values, so that an axis never reads 9.61, 34.61, 59.61. */
export function niceTicks(values, count = 5) {
  const [low, high] = paddedDomain(values);
  const rough = (high - low) / (count - 1) || 1;
  const magnitude = 10 ** Math.floor(Math.log10(rough));
  const step = [1, 2, 2.5, 5, 10].find((option) => option * magnitude >= rough) * magnitude;
  const floor = Math.min(...values) >= 0 ? Math.max(0, low) : low;
  const start = Math.floor(floor / step) * step;
  const ticks = [];
  for (let tick = start; tick < high + step; tick += step) ticks.push(Number(tick.toFixed(6)));
  return ticks;
}

function ChartFrame({ label, table, height = 260, children }) {
  const [showTable, setShowTable] = useState(false);
  return (
    <figure>
      {showTable ? table : <div role="img" aria-label={label} style={{ height }}><ResponsiveContainer width="100%" height="100%">{children}</ResponsiveContainer></div>}
      <figcaption className="mt-2 text-right">
        <button type="button" className="text-xs font-medium text-teal-700 underline" onClick={() => setShowTable((value) => !value)}>
          {showTable ? "Show chart" : "Show as table"}
        </button>
      </figcaption>
    </figure>
  );
}

function ChartTooltip({ active, payload, label, valueFormat, labelFormat }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-md border border-slate-200 bg-white px-3 py-2 text-xs shadow-md">
      <p className="text-slate-500">{labelFormat ? labelFormat(label) : label}</p>
      <p className="tabular mt-0.5 font-semibold text-navy-900">{valueFormat(payload[0].value)}</p>
    </div>
  );
}

/** One measure over time. The card title names it, so a single series needs no legend. */
export function TrendChart({ points, label, currency = "INR", valueFormat, yFormat, xFormat = formatDate, xHeader = "Date", emptyTitle = "No history yet", emptyText, height, valueHeader = "Value" }) {
  if (!points.length) return <Empty title={emptyTitle}>{emptyText}</Empty>;
  const formatValue = valueFormat ?? ((value) => money(value, currency));
  const formatAxis = yFormat ?? ((value) => compactMoney(value, currency));
  const data = points.map((point) => ({ x: point.x, value: Number(point.value), raw: point.value }));
  const ticks = niceTicks(data.map((point) => point.value));
  const table = (
    <DataTable
      columns={[
        { header: xHeader, cell: (row) => xFormat(row.x) },
        { header: valueHeader, cell: (row) => <span className="tabular">{formatValue(row.raw)}</span> },
      ]}
      rows={data}
      rowKey={(row) => row.x}
    />
  );
  return (
    <ChartFrame label={label} table={table} height={height}>
      <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 8 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="x" tickFormatter={xFormat} tick={{ fontSize: 11, fill: AXIS }} tickLine={false} axisLine={{ stroke: GRID }} minTickGap={40} />
        <YAxis domain={[ticks[0], ticks[ticks.length - 1]]} ticks={ticks} interval={0} tickFormatter={formatAxis} tick={{ fontSize: 11, fill: AXIS }} tickLine={false} axisLine={false} width={72} />
        <Tooltip content={<ChartTooltip valueFormat={formatValue} labelFormat={xFormat} />} cursor={{ stroke: AXIS, strokeDasharray: "3 3" }} />
        <Line type="monotone" dataKey="value" stroke={SERIES.teal} strokeWidth={2} dot={data.length <= 24 ? { r: 4, fill: SERIES.teal, stroke: "#fff", strokeWidth: 2 } : false} activeDot={{ r: 5, stroke: "#fff", strokeWidth: 2 }} isAnimationActive={false} />
      </LineChart>
    </ChartFrame>
  );
}

/**
 * Two localities on one index, both starting from the same base, so their lines are directly comparable. A legend names
 * each line and the table view lists every value, so that color is never the only cue.
 */
export function IndexComparison({ series, label, height = 300 }) {
  const lines = series.filter((item) => item.points.length);
  if (!lines.length) return <Empty title="No market data for this locality" />;
  const colors = [SERIES.teal, SERIES.navy];
  const byPeriod = new Map();
  lines.forEach((line, index) => {
    line.points.forEach((point) => {
      const row = byPeriod.get(point.period) ?? { x: point.period };
      row[`s${index}`] = Number(point.price_index);
      byPeriod.set(point.period, row);
    });
  });
  const data = [...byPeriod.values()].sort((a, b) => a.x.localeCompare(b.x));
  const yTicks = niceTicks(data.flatMap((row) => lines.map((_, index) => row[`s${index}`]).filter((value) => value !== undefined)));
  const table = (
    <DataTable
      columns={[{ header: "Month", cell: (row) => formatDate(row.x) }, ...lines.map((line, index) => ({ header: line.name, cell: (row) => <span className="tabular">{row[`s${index}`]?.toFixed(1) ?? "None"}</span> }))]}
      rows={[...data].reverse().slice(0, 36)}
      rowKey={(row) => row.x}
    />
  );
  return (
    <>
      {lines.length > 1 && (
        <ul className="mb-2 flex flex-wrap gap-4 text-xs text-slate-700">
          {lines.map((line, index) => (
            <li key={line.name} className="flex items-center gap-1.5">
              <span aria-hidden className="h-0.5 w-4 rounded" style={{ background: colors[index] }} />
              {line.name}
            </li>
          ))}
        </ul>
      )}
      <ChartFrame label={label} table={table} height={height}>
        <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey="x" ticks={data.map((row) => row.x).filter((x) => x.slice(5, 7) === "01")} tickFormatter={(value) => String(value).slice(0, 4)} tick={{ fontSize: 11, fill: AXIS }} tickLine={false} axisLine={{ stroke: GRID }} minTickGap={24} />
          <YAxis domain={[yTicks[0], yTicks[yTicks.length - 1]]} ticks={yTicks} interval={0} tick={{ fontSize: 11, fill: AXIS }} tickLine={false} axisLine={false} width={44} />
          <Tooltip
            cursor={{ stroke: AXIS, strokeDasharray: "3 3" }}
            content={({ active, payload, label: period }) =>
              active && payload?.length ? (
                <div className="rounded-md border border-slate-200 bg-white px-3 py-2 text-xs shadow-md">
                  <p className="text-slate-500">{formatDate(period)}</p>
                  {payload.map((entry) => (
                    <p key={entry.dataKey} className="tabular mt-0.5 flex items-center gap-1.5 font-medium text-navy-900">
                      <span aria-hidden className="h-0.5 w-3 rounded" style={{ background: entry.stroke }} />
                      {entry.name}: {Number(entry.value).toFixed(1)}
                    </p>
                  ))}
                </div>
              ) : null
            }
          />
          {lines.map((line, index) => (
            <Line key={line.name} type="monotone" name={line.name} dataKey={`s${index}`} stroke={colors[index]} strokeWidth={2} dot={false} activeDot={{ r: 5, stroke: "#fff", strokeWidth: 2 }} connectNulls isAnimationActive={false} />
          ))}
        </LineChart>
      </ChartFrame>
    </>
  );
}

/** Baseline against scenario. Bars are named on the axis and labelled directly, so color is never the only cue. */
export function ComparisonBars({ baseline, scenario, currency = "INR", label }) {
  const data = [
    { name: "Baseline estimate", value: Number(baseline), raw: baseline, fill: SERIES.navy },
    { name: "Hypothetical scenario", value: Number(scenario), raw: scenario, fill: SERIES.teal },
  ];
  const table = (
    <DataTable
      columns={[
        { header: "Measure", cell: (row) => row.name },
        { header: "Value", cell: (row) => <span className="tabular">{money(row.raw, currency)}</span> },
      ]}
      rows={data}
      rowKey={(row) => row.name}
    />
  );
  return (
    <ChartFrame label={label} table={table} height={220}>
      <BarChart data={data} margin={{ top: 24, right: 12, bottom: 0, left: 8 }} barCategoryGap="35%">
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="name" tick={{ fontSize: 12, fill: AXIS }} tickLine={false} axisLine={{ stroke: GRID }} />
        <YAxis domain={[0, "auto"]} tickFormatter={(value) => compactMoney(value, currency)} tick={{ fontSize: 11, fill: AXIS }} tickLine={false} axisLine={false} width={72} />
        <Tooltip content={<ChartTooltip valueFormat={(value) => money(value, currency)} />} cursor={{ fill: "#f1f5f9" }} />
        <Bar dataKey="value" radius={[4, 4, 0, 0]} maxBarSize={72} isAnimationActive={false}>
          {data.map((entry) => (
            <Cell key={entry.name} fill={entry.fill} />
          ))}
          <LabelList dataKey="value" position="top" formatter={(value) => compactMoney(value, currency)} style={{ fontSize: 12, fill: "#0f2038", fontWeight: 600 }} />
        </Bar>
      </BarChart>
    </ChartFrame>
  );
}

/** How much each input moved one estimate. The sign is in the words and the table as well as the color. */
export function FactorBars({ factors, currency = "INR" }) {
  const top = factors.filter((factor) => Number(factor.effect) > 0).slice(0, 6);
  if (!top.length) return <Empty title="No factor detail available" />;
  const data = top.map((factor) => ({ name: factor.factor, value: Number(factor.effect), raw: factor.effect, direction: factor.direction }));
  const table = (
    <DataTable
      columns={[
        { header: "Input", cell: (row) => row.name },
        { header: "Effect", cell: (row) => <span className="tabular">{row.direction} by {money(row.raw, currency)}</span> },
      ]}
      rows={data}
      rowKey={(row) => row.name}
    />
  );
  return (
    <ChartFrame label="How much each input moved this estimate" table={table} height={Math.max(180, top.length * 38)}>
      <BarChart data={data} layout="vertical" margin={{ top: 0, right: 16, bottom: 0, left: 8 }} barCategoryGap="30%">
        <CartesianGrid stroke={GRID} horizontal={false} />
        <XAxis type="number" tickFormatter={(value) => compactMoney(value, currency)} tick={{ fontSize: 11, fill: AXIS }} tickLine={false} axisLine={false} />
        <YAxis type="category" dataKey="name" width={110} tick={{ fontSize: 12, fill: AXIS }} tickLine={false} axisLine={{ stroke: GRID }} />
        <Tooltip content={({ active, payload }) => active && payload?.length ? (
          <div className="rounded-md border border-slate-200 bg-white px-3 py-2 text-xs shadow-md">
            <p className="text-slate-500">{payload[0].payload.name}</p>
            <p className="tabular mt-0.5 font-semibold text-navy-900">{payload[0].payload.direction} the estimate by {money(payload[0].payload.raw, currency)}</p>
          </div>
        ) : null} cursor={{ fill: "#f1f5f9" }} />
        <Bar dataKey="value" radius={[0, 4, 4, 0]} isAnimationActive={false}>
          {data.map((entry) => (
            <Cell key={entry.name} fill={entry.direction === "raises" ? SERIES.teal : SERIES.navy} />
          ))}
        </Bar>
      </BarChart>
    </ChartFrame>
  );
}
