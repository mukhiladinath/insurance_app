'use client';

import { useEffect, useId, useState, type CSSProperties } from 'react';

const LINE_COLORS = ['#4f46e5', '#0ea5e9', '#10b981', '#f59e0b', '#ec4899', '#8b5cf6'];

const currency = (n: unknown) => {
  if (n === null || n === undefined || n === '') return '—';
  const v = typeof n === 'number' ? n : Number(n);
  if (Number.isNaN(v)) return String(n);
  return `$${v.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
};

const pct = (n: unknown) => {
  if (n === null || n === undefined || n === '') return '—';
  const v = typeof n === 'number' ? n : Number(n);
  if (Number.isNaN(v)) return String(n);
  return `${(v * 100).toFixed(1)}%`;
};

const ratioFmt = (n: unknown) => {
  if (n === null || n === undefined || n === '') return '—';
  const v = typeof n === 'number' ? n : Number(n);
  if (Number.isNaN(v)) return String(n);
  return v.toFixed(3);
};

/** Shorter tick labels so they stay left of the plot without overlapping series */
function formatAxisYTick(val: number, valueFormat?: string): string {
  if (valueFormat === 'ratio') return ratioFmt(val);
  if (valueFormat === 'percent') return pct(val);
  const v = Math.abs(val);
  if (v >= 1_000_000) return `$${(val / 1_000_000).toFixed(2)}M`;
  if (v >= 100_000) return `$${(val / 1_000).toFixed(0)}k`;
  if (v >= 10_000) return `$${(val / 1_000).toFixed(1)}k`;
  return `$${Math.round(val).toLocaleString()}`;
}

export type DashboardSpec = {
  title?: string;
  type?: string;
  header?: { title?: string; clientName?: string; source?: string; timestamp?: string };
  summaryCards?: Array<{
    id?: string;
    label?: string;
    value?: unknown;
    format?: string;
  }>;
  charts?: Array<{
    id?: string;
    type?: string;
    title?: string;
    series?: Array<{ name?: string; value?: unknown }>;
    data?: Array<Record<string, unknown>>;
    xKey?: string;
    lines?: Array<{ name?: string; dataKey?: string }>;
    valueFormat?: string;
  }>;
  tables?: Array<{
    id?: string;
    title?: string;
    columns?: string[];
    rows?: unknown[][];
  }>;
  insights?: string[];
  warnings?: string[];
  controls?: Array<{
    id?: string;
    label?: string;
    field?: string;
    inputType?: string;
    options?: number[];
  }>;
  assumptions?: Array<{ label?: string; value?: unknown; format?: string }>;
  /** Per-product dashboard specs when analysis includes multiple insurance types */
  insuranceDashboards?: Record<string, DashboardSpec>;
};

function formatCardValue(value: unknown, format?: string) {
  if (format === 'currency') return currency(value);
  if (format === 'percent') return pct(value);
  if (format === 'ratio') return ratioFmt(value);
  if (format === 'number') return value === null || value === undefined ? '—' : String(value);
  if (format === 'text') return value === null || value === undefined ? '—' : String(value);
  if (typeof value === 'number') return currency(value);
  return value === null || value === undefined ? '—' : String(value);
}

function BarChart({
  title,
  series,
}: {
  title?: string;
  series: Array<{ name?: string; value?: unknown }>;
}) {
  const nums = series.map((s) => {
    const v = s.value;
    if (typeof v === 'number') return v;
    if (v === null || v === undefined) return 0;
    const n = Number(v);
    return Number.isNaN(n) ? 0 : n;
  });
  const max = Math.max(...nums, 1);
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      {title && <h4 className="text-sm font-semibold text-slate-800 mb-3">{title}</h4>}
      <div className="space-y-3">
        {series.map((s, i) => {
          const n = nums[i] ?? 0;
          const w = `${Math.min(100, (n / max) * 100)}%`;
          return (
            <div key={s.name ?? i}>
              <div className="flex justify-between text-xs text-slate-500 mb-1">
                <span>{s.name}</span>
                <span>{currency(n)}</span>
              </div>
              <div className="h-2 rounded-full bg-slate-100 overflow-hidden">
                <div
                  className="h-full rounded-full bg-indigo-500"
                  style={{ width: w } as CSSProperties}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function LineChart({
  title,
  data,
  xKey,
  lines,
  valueFormat,
}: {
  title?: string;
  data: Array<Record<string, unknown>>;
  xKey?: string;
  lines?: Array<{ name?: string; dataKey?: string }>;
  valueFormat?: string;
}) {
  const clipId = `chart-clip-${useId().replace(/[^a-zA-Z0-9_-]/g, '')}`;
  const xk = xKey ?? 'year';
  if (!data?.length) return null;
  const keys = (lines ?? [])
    .map((l) => l.dataKey)
    .filter((k): k is string => typeof k === 'string' && k.length > 0);

  const numericRows = data.map((row) =>
    keys.map((k) => {
      const raw = row[k];
      if (raw === null || raw === undefined) return 0;
      const n = Number(raw);
      return Number.isNaN(n) ? 0 : n;
    }),
  );
  const flatMax = Math.max(1e-6, ...numericRows.flat());
  let scaleMax = flatMax;
  if (valueFormat === 'ratio' || valueFormat === 'percent') {
    scaleMax = Math.min(2, Math.max(0.05, flatMax * 1.1));
  } else {
    scaleMax = flatMax * 1.06;
  }

  const w = 520;
  const h = 176;
  const padL = 92;
  const padR = 20;
  const padT = 14;
  const padB = 36;
  const innerW = w - padL - padR;
  const innerH = h - padT - padB;

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      {title && <h4 className="text-sm font-semibold text-slate-800 mb-3">{title}</h4>}
      <div className="overflow-x-auto">
        <svg viewBox={`0 0 ${w} ${h}`} className="w-full min-w-[360px]" style={{ maxHeight: 220 }}>
          <defs>
            <clipPath id={clipId}>
              <rect x={padL} y={padT} width={innerW} height={innerH} />
            </clipPath>
          </defs>
          {[0, 0.25, 0.5, 0.75, 1].map((t) => {
            const tickVal = scaleMax * t;
            const yv = padT + innerH * (1 - t);
            return (
              <g key={t}>
                <text
                  x={padL - 10}
                  y={yv}
                  textAnchor="end"
                  dominantBaseline="central"
                  className="fill-slate-500"
                  style={{ fontSize: 10 }}
                >
                  {formatAxisYTick(tickVal, valueFormat)}
                </text>
              </g>
            );
          })}
          <g clipPath={`url(#${clipId})`}>
            {[0, 0.25, 0.5, 0.75, 1].map((t) => {
              const yv = padT + innerH * (1 - t);
              return (
                <line
                  key={`g-${t}`}
                  x1={padL}
                  y1={yv}
                  x2={w - padR}
                  y2={yv}
                  stroke="#e2e8f0"
                  strokeWidth="1"
                />
              );
            })}
            {keys.map((k, ki) => {
              const pts = data
                .map((row, i) => {
                  const xv = padL + (i / Math.max(1, data.length - 1)) * innerW;
                  const yvNum = Number(row[k]) || 0;
                  const yn = padT + innerH * (1 - yvNum / scaleMax);
                  return `${xv},${yn}`;
                })
                .join(' ');
              return (
                <polyline
                  key={k}
                  fill="none"
                  stroke={LINE_COLORS[ki % LINE_COLORS.length]}
                  strokeWidth="2"
                  strokeLinejoin="round"
                  strokeLinecap="round"
                  points={pts}
                />
              );
            })}
          </g>
          <line
            x1={padL}
            y1={padT + innerH}
            x2={w - padR}
            y2={padT + innerH}
            stroke="#cbd5e1"
            strokeWidth="1"
          />
          {data.map((row, i) => {
            const xv = padL + (i / Math.max(1, data.length - 1)) * innerW;
            const label = String(row[xk]);
            const showTick = data.length <= 16 || i % Math.ceil(data.length / 12) === 0 || i === data.length - 1;
            if (!showTick) return null;
            return (
              <text
                key={`x-${i}`}
                x={xv}
                y={h - 10}
                textAnchor="middle"
                className="fill-slate-500"
                style={{ fontSize: 9 }}
              >
                {label}
              </text>
            );
          })}
        </svg>
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-600 mt-2">
          {lines?.map((l, i) => (
            <span key={l.dataKey} className="inline-flex items-center gap-1.5">
              <span
                className="inline-block w-2.5 h-0.5 rounded"
                style={{ background: LINE_COLORS[i % LINE_COLORS.length] }}
              />
              <span className="font-medium">{l.name}</span>
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

interface Props {
  spec: DashboardSpec;
  projectionData?: Record<string, unknown>;
}

const TAB_LABEL: Record<string, string> = {
  life: 'Life',
  tpd: 'TPD',
  income_protection: 'Income protection',
};

export default function DynamicInsuranceDashboardRenderer({ spec, projectionData }: Props) {
  const nested = spec.insuranceDashboards;
  const tabKeys = nested ? Object.keys(nested) : [];
  const showTabs = tabKeys.length > 1;
  const [tab, setTab] = useState(tabKeys[0] ?? 'life');

  useEffect(() => {
    if (tabKeys.length) setTab(tabKeys[0]);
  }, [spec.title, tabKeys.join('|')]);

  const viewSpec: DashboardSpec =
    showTabs && nested && tab
      ? (nested[tab] as DashboardSpec)
      : tabKeys.length === 1 && nested
        ? (nested[tabKeys[0]] as DashboardSpec)
        : spec;

  const pdNested = (projectionData as { insuranceDashboards?: Record<string, unknown> } | undefined)
    ?.insuranceDashboards;
  const viewProjection: Record<string, unknown> | undefined =
    showTabs && tab && pdNested?.[tab]
      ? (pdNested[tab] as Record<string, unknown>)
      : tabKeys.length === 1 && pdNested?.[tabKeys[0]]
        ? (pdNested[tabKeys[0]] as Record<string, unknown>)
        : projectionData;

  const h = viewSpec.header;
  return (
    <div className="space-y-6">
      {showTabs && (
        <div className="flex flex-wrap gap-1 border-b border-slate-200 pb-2">
          {tabKeys.map((k) => (
            <button
              key={k}
              type="button"
              onClick={() => setTab(k)}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                tab === k
                  ? 'bg-indigo-600 text-white'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
            >
              {TAB_LABEL[k] ?? k}
            </button>
          ))}
        </div>
      )}

      <div className="border-b border-slate-200 pb-4">
        <h2 className="text-lg font-semibold text-slate-900">{h?.title ?? viewSpec.title}</h2>
        <p className="text-sm text-slate-500 mt-1">
          {h?.clientName ? `${h.clientName} · ` : ''}
          {h?.source ?? ''}
          {h?.timestamp ? ` · ${h.timestamp}` : ''}
        </p>
      </div>

      {viewSpec.summaryCards && viewSpec.summaryCards.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {viewSpec.summaryCards.map((c) => (
            <div
              key={c.id ?? c.label}
              className="rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm"
            >
              <p className="text-xs font-medium text-slate-500 uppercase tracking-wide">{c.label}</p>
              <p className="text-lg font-semibold text-slate-900 mt-1 tabular-nums">
                {formatCardValue(c.value, c.format)}
              </p>
            </div>
          ))}
        </div>
      )}

      {viewSpec.controls && viewSpec.controls.length > 0 && (
        <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50/80 px-4 py-3">
          <h4 className="text-xs font-semibold text-slate-600 uppercase tracking-wide mb-2">
            Projection controls (regenerate via Dashboards tab)
          </h4>
          <ul className="text-xs text-slate-600 space-y-1 list-disc pl-4">
            {viewSpec.controls.map((c) => (
              <li key={c.id ?? c.label}>
                <span className="font-medium">{c.label}</span>
                {c.field ? ` → ${c.field}` : ''}
                {c.options ? ` (options: ${c.options.join(', ')})` : ''}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="space-y-6">
        {viewSpec.charts?.map((ch) => {
          if (ch.type === 'bar' && ch.series) {
            return <BarChart key={ch.id ?? ch.title} title={ch.title} series={ch.series} />;
          }
          if (ch.type === 'line' && ch.data && ch.lines) {
            return (
              <LineChart
                key={ch.id ?? ch.title}
                title={ch.title}
                data={ch.data}
                xKey={ch.xKey}
                lines={ch.lines}
                valueFormat={ch.valueFormat}
              />
            );
          }
          return null;
        })}
      </div>

      {viewSpec.tables?.map((t) => (
        <div key={t.id ?? t.title} className="rounded-xl border border-slate-200 overflow-hidden">
          {t.title && (
            <div className="px-4 py-2 bg-slate-50 border-b border-slate-100 text-sm font-semibold text-slate-800">
              {t.title}
            </div>
          )}
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-slate-500 border-b border-slate-100">
                  {t.columns?.map((col) => (
                    <th key={col} className="px-4 py-2 font-medium">
                      {col}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {t.rows?.map((row, ri) => (
                  <tr key={ri} className="border-b border-slate-50">
                    {row.map((cell, ci) => (
                      <td key={ci} className="px-4 py-2 text-slate-800">
                        {cell === null || cell === undefined ? '—' : String(cell)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}

      {viewSpec.insights && viewSpec.insights.length > 0 && (
        <div className="rounded-xl border border-slate-200 bg-indigo-50/50 px-4 py-3">
          <h4 className="text-xs font-semibold text-indigo-900 uppercase tracking-wide mb-2">Insights</h4>
          <ul className="list-disc pl-4 text-sm text-slate-700 space-y-1">
            {viewSpec.insights.map((i, idx) => (
              <li key={idx}>{i}</li>
            ))}
          </ul>
        </div>
      )}

      {viewSpec.warnings && viewSpec.warnings.length > 0 && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3">
          <h4 className="text-xs font-semibold text-amber-900 uppercase tracking-wide mb-2">Warnings</h4>
          <ul className="list-disc pl-4 text-sm text-amber-900 space-y-1">
            {viewSpec.warnings.map((w, idx) => (
              <li key={idx}>{w}</li>
            ))}
          </ul>
        </div>
      )}

      {viewSpec.assumptions && viewSpec.assumptions.length > 0 && (
        <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600">
          <h4 className="text-xs font-semibold text-slate-600 uppercase tracking-wide mb-2">Assumptions</h4>
          <ul className="space-y-1">
            {viewSpec.assumptions.map((a, i) => (
              <li key={i}>
                <span className="text-slate-500">{a.label}: </span>
                {formatCardValue(a.value, a.format)}
              </li>
            ))}
          </ul>
        </div>
      )}

      {viewProjection &&
        (viewProjection as { yearlySeries?: unknown[] }).yearlySeries &&
        (viewProjection as { yearlySeries: unknown[] }).yearlySeries.length > 0 && (
          <details className="text-xs text-slate-400">
            <summary className="cursor-pointer">Year-by-year projection series</summary>
            <pre className="mt-2 p-2 bg-slate-50 rounded overflow-x-auto max-h-40">
              {JSON.stringify((viewProjection as { yearlySeries: unknown[] }).yearlySeries, null, 2)}
            </pre>
          </details>
        )}
    </div>
  );
}
