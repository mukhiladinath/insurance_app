'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Loader2,
  RefreshCw,
  GitCompare,
  Save,
  AlertTriangle,
  ChevronDown,
  ChevronRight,
} from 'lucide-react';
import {
  compareInsuranceToolRuns,
  listInsuranceToolRuns,
  listSavedInsuranceComparisons,
  saveInsuranceComparison,
  type InsuranceToolRunListItem,
  type SavedInsuranceComparisonSummary,
} from '../../lib/api';
import MarkdownProse from '../ui/MarkdownProse';
import type { PendingInsuranceComparison } from '../../store/client-store';

const MODE_BADGE: Record<string, string> = {
  direct: 'bg-emerald-50 text-emerald-800 border-emerald-200',
  partial: 'bg-amber-50 text-amber-800 border-amber-200',
  scenario: 'bg-violet-50 text-violet-800 border-violet-200',
};

const DELTA_BADGE: Record<string, string> = {
  increase: 'text-amber-700 bg-amber-50',
  decrease: 'text-sky-700 bg-sky-50',
  same: 'text-slate-600 bg-slate-100',
  not_applicable: 'text-slate-400 bg-slate-50',
};

function moneyOrText(v: unknown): string {
  if (v === null || v === undefined) return '—';
  if (typeof v === 'number') return v >= 1000 ? `$${v.toLocaleString()}` : String(v);
  return String(v);
}

function formatToolTitle(name: unknown): string {
  if (typeof name !== 'string' || !name.trim()) return 'Analysis';
  return name.replace(/_/g, ' ');
}

/** Cover cell: money, boolean, or em dash — used for scenario two-column layout. */
function formatCoverCell(v: unknown): string {
  if (v === null || v === undefined) return '—';
  if (typeof v === 'boolean') return v ? 'Yes' : 'No';
  if (typeof v === 'number') return moneyOrText(v);
  return String(v);
}

const SCENARIO_COVER_ROWS: Array<{ key: string; label: string }> = [
  { key: 'life', label: 'Life cover' },
  { key: 'tpd', label: 'TPD cover' },
  { key: 'trauma', label: 'Trauma cover' },
  { key: 'incomeProtectionMonthly', label: 'IP monthly benefit' },
  { key: 'incomeProtectionReplacementRatio', label: 'IP replacement ratio' },
  { key: 'waitingPeriod', label: 'Waiting period' },
  { key: 'benefitPeriod', label: 'Benefit period' },
  { key: 'ownOccupationTPD', label: 'Own occupation TPD' },
  { key: 'anyOccupationTPD', label: 'Any occupation TPD' },
  { key: 'heldInsideSuper', label: 'Held inside super' },
  { key: 'splitOwnership', label: 'Split ownership' },
];

/**
 * When comparing different tools (scenario mode), a row-per-fact table misleads: Life vs TPD
 * are not the same metric. Show two columns — full first analysis vs full second analysis.
 */
function ScenarioCoverColumns({
  left,
  right,
}: {
  left: Record<string, unknown> | undefined;
  right: Record<string, unknown> | undefined;
}) {
  const lc = (left?.cover as Record<string, unknown>) ?? {};
  const rc = (right?.cover as Record<string, unknown>) ?? {};
  const lt = formatToolTitle(left?.toolName);
  const rt = formatToolTitle(right?.toolName);

  return (
    <div className="space-y-3">
      <p className="text-xs text-slate-500 px-4 leading-relaxed">
        <strong>Option A</strong> is the first analysis you selected; <strong>Option B</strong> is the second. Each
        column lists all cover fields for that analysis — they are not paired as identical metrics when the tools
        differ (e.g. life-focused vs TPD-focused).
      </p>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 px-4 pb-4">
        <div className="rounded-lg border border-slate-200 bg-slate-50/50 p-4">
          <p className="text-xs font-semibold text-slate-600 uppercase tracking-wide mb-1">Option A</p>
          <p className="text-[11px] text-indigo-600 font-medium mb-3">{lt}</p>
          <dl className="space-y-2">
            {SCENARIO_COVER_ROWS.map(({ key, label }) => (
              <div
                key={key}
                className="flex justify-between gap-3 text-xs border-b border-slate-100 pb-2 last:border-0 last:pb-0"
              >
                <dt className="text-slate-500 shrink-0">{label}</dt>
                <dd className="text-slate-900 font-medium text-right tabular-nums">{formatCoverCell(lc[key])}</dd>
              </div>
            ))}
          </dl>
        </div>
        <div className="rounded-lg border border-slate-200 bg-slate-50/50 p-4">
          <p className="text-xs font-semibold text-slate-600 uppercase tracking-wide mb-1">Option B</p>
          <p className="text-[11px] text-indigo-600 font-medium mb-3">{rt}</p>
          <dl className="space-y-2">
            {SCENARIO_COVER_ROWS.map(({ key, label }) => (
              <div
                key={`${key}-r`}
                className="flex justify-between gap-3 text-xs border-b border-slate-100 pb-2 last:border-0 last:pb-0"
              >
                <dt className="text-slate-500 shrink-0">{label}</dt>
                <dd className="text-slate-900 font-medium text-right tabular-nums">{formatCoverCell(rc[key])}</dd>
              </div>
            ))}
          </dl>
        </div>
      </div>
    </div>
  );
}

interface Props {
  clientId: string;
  initialLeftToolRunId?: string | null;
  preloadedComparison?: PendingInsuranceComparison | null;
  onPreloadedComparisonConsumed?: () => void;
}

export default function InsuranceComparisonPanel({
  clientId,
  initialLeftToolRunId,
  preloadedComparison,
  onPreloadedComparisonConsumed,
}: Props) {
  const [runs, setRuns] = useState<InsuranceToolRunListItem[]>([]);
  const [saved, setSaved] = useState<SavedInsuranceComparisonSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [comparing, setComparing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [leftId, setLeftId] = useState('');
  const [rightId, setRightId] = useState('');
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>({});

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [r, s] = await Promise.all([
        listInsuranceToolRuns(clientId, 120),
        listSavedInsuranceComparisons(clientId, 30),
      ]);
      setRuns(r);
      setSaved(s);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Load failed');
    } finally {
      setLoading(false);
    }
  }, [clientId]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (initialLeftToolRunId && !leftId) {
      setLeftId(initialLeftToolRunId);
    }
  }, [initialLeftToolRunId, leftId]);

  useEffect(() => {
    if (!preloadedComparison) return;
    setLeftId(preloadedComparison.leftToolRunId);
    setRightId(preloadedComparison.rightToolRunId);
    setResult(preloadedComparison.result);
    setError(null);
    onPreloadedComparisonConsumed?.();
  }, [preloadedComparison, onPreloadedComparisonConsumed]);

  const groupedRows = useMemo(() => {
    const facts = (result?.factsTable as Array<Record<string, unknown>>) ?? [];
    const m: Record<string, Array<Record<string, unknown>>> = {};
    for (const row of facts) {
      const g = String(row.group ?? 'Other');
      if (!m[g]) m[g] = [];
      m[g].push(row);
    }
    return m;
  }, [result]);

  const runCompare = async () => {
    if (!leftId || !rightId || leftId === rightId) {
      setError('Select two different saved tool outputs.');
      return;
    }
    setComparing(true);
    setError(null);
    try {
      const res = await compareInsuranceToolRuns({
        clientId,
        leftToolRunId: leftId,
        rightToolRunId: rightId,
      });
      setResult(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Compare failed');
      setResult(null);
    } finally {
      setComparing(false);
    }
  };

  const saveIt = async () => {
    if (!result || !leftId || !rightId) return;
    setSaving(true);
    setError(null);
    try {
      await saveInsuranceComparison({
        clientId,
        leftToolRunId: leftId,
        rightToolRunId: rightId,
        comparisonResult: result,
      });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  const leftCard = result?.left as Record<string, unknown> | undefined;
  const rightCard = result?.right as Record<string, unknown> | undefined;
  const mergedWarnings = useMemo(() => {
    const lw = leftCard?.warnings;
    const rw = rightCard?.warnings;
    const a = [...(Array.isArray(lw) ? lw : []), ...(Array.isArray(rw) ? rw : [])].filter(
      (x): x is string => typeof x === 'string' && Boolean(x),
    );
    return a.length ? [...new Set(a)] : (['None recorded in normalized output.'] as const);
  }, [leftCard?.warnings, rightCard?.warnings]);
  const mode = String(result?.comparisonMode ?? '');
  const insights = (result?.insights as Record<string, unknown>) ?? {};
  const riskFlags = (result?.riskFlags as Array<Record<string, unknown>>) ?? [];
  const narrative = String(result?.narrativeSummary ?? '');

  return (
    <div className="space-y-4">
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
        <div className="px-5 py-3 bg-slate-50 border-b border-slate-100 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <GitCompare size={15} className="text-indigo-500" />
            <h3 className="text-xs font-semibold text-slate-600 uppercase tracking-wider">Compare tool outputs</h3>
          </div>
          <button
            type="button"
            onClick={() => load()}
            disabled={loading}
            className="p-1.5 text-slate-400 hover:text-slate-700 hover:bg-slate-100 rounded-lg transition-colors disabled:opacity-50"
            aria-label="Refresh"
          >
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>

        <div className="p-5 space-y-4">
          {error && (
            <div className="text-xs text-red-700 bg-red-50 border border-red-100 rounded-lg px-3 py-2">{error}</div>
          )}

          <p className="text-sm text-slate-600">
            Pick two completed insurance tool outputs: from <strong>workspace saves</strong> or from <strong>saved analyses</strong> (AI bar runs). Comparison uses normalized facts, not prose diffs. Ask the AI bar to &quot;compare&quot; two products to run both tools and open this tab with a result.
          </p>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <label className="block text-xs font-medium text-slate-500 uppercase tracking-wide">
              Option A (left)
              <select
                className="mt-1 w-full text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white"
                value={leftId}
                onChange={(e) => setLeftId(e.target.value)}
                disabled={loading}
              >
                <option value="">Select…</option>
                {runs.map((r) => (
                  <option key={r.toolRunId} value={r.toolRunId}>
                    {r.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="block text-xs font-medium text-slate-500 uppercase tracking-wide">
              Option B (right)
              <select
                className="mt-1 w-full text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white"
                value={rightId}
                onChange={(e) => setRightId(e.target.value)}
                disabled={loading}
              >
                <option value="">Select…</option>
                {runs.map((r) => (
                  <option key={`${r.toolRunId}-r`} value={r.toolRunId}>
                    {r.label}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => void runCompare()}
              disabled={comparing || loading}
              className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50"
            >
              {comparing ? <Loader2 size={14} className="animate-spin" /> : <GitCompare size={14} />}
              Compare
            </button>
            <button
              type="button"
              onClick={() => void saveIt()}
              disabled={saving || !result}
              className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium border border-slate-200 rounded-lg text-slate-700 hover:bg-slate-50 disabled:opacity-50"
            >
              {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
              Save comparison
            </button>
          </div>
        </div>
      </div>

      {saved.length > 0 && (
        <div className="bg-white rounded-xl border border-slate-200 p-4">
          <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">Saved comparisons</h4>
          <ul className="text-sm text-slate-600 space-y-1">
            {saved.map((s) => (
              <li key={s.id} className="flex flex-wrap gap-x-2">
                <span className="font-medium text-slate-800">{s.comparisonMode}</span>
                <span className="text-slate-400">·</span>
                <span>{s.leftToolName}</span>
                <span>vs</span>
                <span>{s.rightToolName}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {result && (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={`text-xs font-semibold uppercase tracking-wide px-2 py-1 rounded border ${MODE_BADGE[mode] ?? 'bg-slate-50 text-slate-600 border-slate-200'}`}
            >
              {mode || 'unknown'} mode
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div className="bg-white rounded-xl border border-slate-200 p-4">
              <p className="text-xs font-semibold text-slate-400 uppercase mb-1">Option A</p>
              <p className="text-sm font-semibold text-slate-800">{String(leftCard?.toolName ?? '')}</p>
              <p className="text-xs text-slate-500 mt-1 line-clamp-3">
                {(leftCard?.scenarioSummary as Record<string, string> | undefined)?.description ?? ''}
              </p>
              <div className="mt-2 text-xs text-slate-600 space-y-0.5">
                <div>Cover life: {moneyOrText((leftCard?.cover as Record<string, unknown>)?.life)}</div>
                <div>Annual premium: {moneyOrText((leftCard?.premiums as Record<string, unknown>)?.annual)}</div>
              </div>
            </div>
            <div className="bg-white rounded-xl border border-slate-200 p-4">
              <p className="text-xs font-semibold text-slate-400 uppercase mb-1">Option B</p>
              <p className="text-sm font-semibold text-slate-800">{String(rightCard?.toolName ?? '')}</p>
              <p className="text-xs text-slate-500 mt-1 line-clamp-3">
                {(rightCard?.scenarioSummary as Record<string, string> | undefined)?.description ?? ''}
              </p>
              <div className="mt-2 text-xs text-slate-600 space-y-0.5">
                <div>Cover life: {moneyOrText((rightCard?.cover as Record<string, unknown>)?.life)}</div>
                <div>Annual premium: {moneyOrText((rightCard?.premiums as Record<string, unknown>)?.annual)}</div>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div className="bg-amber-50/80 border border-amber-100 rounded-xl p-4">
              <p className="text-xs font-semibold text-amber-800 uppercase mb-2">Warnings (merged)</p>
              <ul className="text-xs text-amber-900 space-y-1 list-disc pl-4 max-h-32 overflow-y-auto">
                {mergedWarnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            </div>
            <div className="bg-slate-50 border border-slate-200 rounded-xl p-4">
              <p className="text-xs font-semibold text-slate-600 uppercase mb-2">Weighted scores (where available)</p>
              <pre className="text-[11px] text-slate-700 whitespace-pre-wrap font-mono">
                {JSON.stringify(result.weightedTotals ?? {}, null, 0)}
              </pre>
              {result.scoreExplanation ? (
                <p className="text-xs text-slate-500 mt-2">{String(result.scoreExplanation)}</p>
              ) : null}
            </div>
          </div>

          <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
            <div className="px-4 py-2 bg-slate-50 border-b border-slate-100 text-xs font-semibold text-slate-600 uppercase">
              Fact table
            </div>
            <div className="divide-y divide-slate-100">
              {Object.entries(groupedRows).map(([group, rows]) => {
                const open = openGroups[group] ?? true;
                const coverScenarioLayout = group === 'Cover' && mode === 'scenario';

                return (
                  <div key={group}>
                    <button
                      type="button"
                      className="w-full flex items-center gap-2 px-4 py-2 text-left text-sm font-semibold text-slate-700 hover:bg-slate-50"
                      onClick={() => setOpenGroups((o) => ({ ...o, [group]: !open }))}
                    >
                      {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                      {group}
                    </button>
                    {open &&
                      (coverScenarioLayout ? (
                        <ScenarioCoverColumns left={leftCard} right={rightCard} />
                      ) : (
                        <div className="overflow-x-auto">
                          <table className="w-full text-xs">
                            <thead>
                              <tr className="text-left text-slate-500 border-t border-slate-100">
                                <th className="px-4 py-2 font-medium">Fact</th>
                                <th className="px-4 py-2 font-medium">Option A</th>
                                <th className="px-4 py-2 font-medium">Option B</th>
                                <th className="px-4 py-2 font-medium">Delta</th>
                              </tr>
                            </thead>
                            <tbody>
                              {rows.map((row) => {
                                const dt = String(row.deltaType ?? 'not_applicable');
                                return (
                                  <tr key={String(row.key)} className="border-t border-slate-50">
                                    <td className="px-4 py-2 text-slate-700">{String(row.label)}</td>
                                    <td className="px-4 py-2 text-slate-800">{String(row.leftDisplay)}</td>
                                    <td className="px-4 py-2 text-slate-800">{String(row.rightDisplay)}</td>
                                    <td className="px-4 py-2">
                                      <span
                                        className={`rounded px-1.5 py-0.5 ${DELTA_BADGE[dt] ?? DELTA_BADGE.not_applicable}`}
                                      >
                                        {dt.replace(/_/g, ' ')}
                                      </span>
                                      <div className="text-slate-500 mt-0.5">{String(row.differenceSummary ?? '')}</div>
                                    </td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                      ))}
                  </div>
                );
              })}
            </div>
          </div>

          {(insights.majorDifferences as string[] | undefined)?.length ? (
            <div className="bg-white rounded-xl border border-slate-200 p-4">
              <p className="text-xs font-semibold text-slate-600 uppercase mb-2">Major differences</p>
              <ul className="text-sm text-slate-700 space-y-1 list-disc pl-4">
                {(insights.majorDifferences as string[]).map((x, i) => (
                  <li key={i}>{x}</li>
                ))}
              </ul>
            </div>
          ) : null}

          {riskFlags.length > 0 && (
            <div className="bg-red-50/80 border border-red-100 rounded-xl p-4">
              <p className="flex items-center gap-2 text-xs font-semibold text-red-800 uppercase mb-2">
                <AlertTriangle size={14} /> Risks / flags
              </p>
              <ul className="text-xs text-red-900 space-y-1">
                {riskFlags.map((f, i) => (
                  <li key={i}>
                    <span className="font-semibold">{String(f.severity)}:</span> {String(f.message)}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="bg-white rounded-xl border border-slate-200 p-4">
            <p className="text-xs font-semibold text-slate-600 uppercase mb-2">Adviser summary</p>
            <MarkdownProse content={narrative} />
          </div>
        </>
      )}
    </div>
  );
}
