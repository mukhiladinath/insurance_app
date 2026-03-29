'use client';

import { useState, useEffect, useCallback } from 'react';
import { Loader2, RefreshCw, LayoutDashboard } from 'lucide-react';
import DynamicInsuranceDashboardRenderer, { type DashboardSpec } from './DynamicInsuranceDashboardRenderer';
import type { PendingInsuranceDashboard } from '../../store/client-store';

const BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

type DashboardRow = {
  id: string;
  title: string;
  dashboard_type: string;
  created_at: string;
};

type ListResponse = {
  client_id: string;
  dashboards: DashboardRow[];
};

type DashboardDetail = {
  id: string;
  dashboard_spec: DashboardSpec;
  projection_data: Record<string, unknown>;
  resolved_inputs?: Record<string, unknown>;
  dashboard_type: string;
  title: string;
};

async function fetchList(clientId: string): Promise<ListResponse> {
  const res = await fetch(`${BASE}/api/clients/${clientId}/insurance-dashboards`);
  if (!res.ok) throw new Error(`Failed to load dashboards (${res.status})`);
  return res.json();
}

async function fetchOne(clientId: string, dashboardId: string): Promise<DashboardDetail> {
  const res = await fetch(`${BASE}/api/clients/${clientId}/insurance-dashboards/${dashboardId}`);
  if (!res.ok) throw new Error(`Failed to load dashboard (${res.status})`);
  return res.json();
}

async function regenerate(
  clientId: string,
  dashboardId: string,
  overrides: Record<string, unknown>,
): Promise<DashboardDetail> {
  const res = await fetch(`${BASE}/api/clients/${clientId}/insurance-dashboards/${dashboardId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ overrides }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err?.detail ?? `Regenerate failed (${res.status})`);
  }
  return res.json();
}

interface Props {
  clientId: string;
  preloaded?: PendingInsuranceDashboard | null;
  onPreloadedConsumed?: () => void;
}

export default function InsuranceDashboardsPanel({ clientId, preloaded, onPreloadedConsumed }: Props) {
  const [list, setList] = useState<DashboardRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<DashboardDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [regenCover, setRegenCover] = useState('');
  const [regenHorizon, setRegenHorizon] = useState<10 | 15 | 20 | 25>(15);
  const [regenDepSupport, setRegenDepSupport] = useState('');
  const [regenIncomeSupport, setRegenIncomeSupport] = useState('');
  const [regenDebtPayoff, setRegenDebtPayoff] = useState('');
  const [regenPremTol, setRegenPremTol] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchList(clientId);
      setList(data.dashboards);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Load failed');
    } finally {
      setLoading(false);
    }
  }, [clientId]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const onCreated = (e: Event) => {
      const d = (e as CustomEvent<{ clientId?: string }>).detail;
      if (d?.clientId === clientId) load();
    };
    window.addEventListener('insurance-dashboard-created', onCreated);
    return () => window.removeEventListener('insurance-dashboard-created', onCreated);
  }, [clientId, load]);

  useEffect(() => {
    if (preloaded?.clientId === clientId && preloaded.dashboardId) {
      setSelectedId(preloaded.dashboardId);
      onPreloadedConsumed?.();
    }
  }, [preloaded, clientId, onPreloadedConsumed]);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    setDetailLoading(true);
    void fetchOne(clientId, selectedId)
      .then((d) => {
        if (!cancelled) setDetail(d);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Load failed');
      })
      .finally(() => {
        if (!cancelled) setDetailLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [clientId, selectedId]);

  useEffect(() => {
    if (!detail?.resolved_inputs) return;
    const ri = detail.resolved_inputs;
    const h = Number(ri.projection_horizon);
    if (h === 10 || h === 15 || h === 20 || h === 25) setRegenHorizon(h);
    const fmt = (x: unknown) => (x === null || x === undefined ? '' : String(x));
    setRegenDepSupport(fmt(ri.dependent_support_decay_years));
    setRegenIncomeSupport(fmt(ri.income_support_years));
    setRegenDebtPayoff(fmt(ri.debt_payoff_years));
    setRegenPremTol(fmt(ri.premium_tolerance_ratio));
  }, [detail?.id, detail?.resolved_inputs]);

  const handleRegenerate = async () => {
    if (!selectedId) return;
    const overrides: Record<string, unknown> = {
      'dashboard.projection_horizon': regenHorizon,
    };
    if (regenCover.trim()) {
      const v = Number(regenCover.replace(/[^\d.]/g, ''));
      if (Number.isNaN(v)) {
        setError('Recommended cover must be a number.');
        return;
      }
      overrides['dashboard.recommended_life_cover'] = v;
    }
    const parseOpt = (s: string) => {
      const t = s.trim();
      if (!t) return undefined;
      const n = Number(t.replace(/[^\d.]/g, ''));
      return Number.isNaN(n) ? undefined : n;
    };
    const parseTol = (s: string) => {
      const t = s.trim();
      if (!t) return undefined;
      const n = Number(t);
      return Number.isNaN(n) ? undefined : n;
    };
    const ds = parseOpt(regenDepSupport);
    const isy = parseOpt(regenIncomeSupport);
    const dpy = parseOpt(regenDebtPayoff);
    const pt = parseTol(regenPremTol);
    if (ds !== undefined) overrides['dashboard.dependent_support_decay_years'] = ds;
    if (isy !== undefined) overrides['dashboard.income_support_years'] = isy;
    if (dpy !== undefined) overrides['dashboard.debt_payoff_years'] = dpy;
    if (pt !== undefined) overrides['dashboard.premium_tolerance_ratio'] = pt;

    setDetailLoading(true);
    setError(null);
    try {
      const d = await regenerate(clientId, selectedId, overrides);
      setDetail(d);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Regenerate failed');
    } finally {
      setDetailLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-semibold text-slate-600 uppercase tracking-wider flex items-center gap-2">
          <LayoutDashboard size={14} />
          Insurance dashboards
        </h3>
        <button
          type="button"
          onClick={() => load()}
          className="p-1.5 text-slate-400 hover:text-slate-700 rounded"
          title="Refresh"
        >
          <RefreshCw size={14} />
        </button>
      </div>

      {loading && (
        <div className="flex items-center gap-2 text-sm text-slate-500">
          <Loader2 size={16} className="animate-spin" />
          Loading…
        </div>
      )}
      {error && <div className="text-sm text-red-600">{error}</div>}

      {!loading && list.length === 0 && (
        <p className="text-sm text-slate-500 py-6">
          No dashboards yet. Ask the AI bar to create an insurance dashboard (e.g. &quot;Create an insurance needs
          dashboard&quot;) after you have at least one saved analysis.
        </p>
      )}

      {list.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {list.map((d) => (
            <button
              key={d.id}
              type="button"
              onClick={() => setSelectedId(d.id)}
              className={`px-3 py-1.5 rounded-lg text-sm border ${
                selectedId === d.id
                  ? 'bg-indigo-50 border-indigo-200 text-indigo-900'
                  : 'bg-white border-slate-200 text-slate-700 hover:bg-slate-50'
              }`}
            >
              {d.title || d.dashboard_type}
            </button>
          ))}
        </div>
      )}

      {selectedId && (
        <div className="border border-slate-200 rounded-xl p-4 bg-white">
          <div className="space-y-3 mb-4">
            <p className="text-xs text-slate-500">
              Deterministic projections update when you regenerate. Leave fields blank to keep stored values.
            </p>
            <div className="flex flex-wrap gap-3 items-end">
              <div>
                <label className="block text-xs text-slate-500 mb-1">Projection horizon (years)</label>
                <select
                  value={regenHorizon}
                  onChange={(e) => setRegenHorizon(Number(e.target.value) as 10 | 15 | 20 | 25)}
                  className="border border-slate-200 rounded-lg px-3 py-1.5 text-sm bg-white"
                >
                  {[10, 15, 20, 25].map((y) => (
                    <option key={y} value={y}>
                      {y}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs text-slate-500 mb-1">Recommended cover override</label>
                <input
                  type="text"
                  value={regenCover}
                  onChange={(e) => setRegenCover(e.target.value)}
                  placeholder="optional, e.g. 500000"
                  className="border border-slate-200 rounded-lg px-3 py-1.5 text-sm w-40"
                />
              </div>
              <div>
                <label className="block text-xs text-slate-500 mb-1">Dependent support taper (years)</label>
                <input
                  type="text"
                  value={regenDepSupport}
                  onChange={(e) => setRegenDepSupport(e.target.value)}
                  placeholder="optional"
                  className="border border-slate-200 rounded-lg px-3 py-1.5 text-sm w-28"
                />
              </div>
              <div>
                <label className="block text-xs text-slate-500 mb-1">Income support (years)</label>
                <input
                  type="text"
                  value={regenIncomeSupport}
                  onChange={(e) => setRegenIncomeSupport(e.target.value)}
                  placeholder="optional"
                  className="border border-slate-200 rounded-lg px-3 py-1.5 text-sm w-28"
                />
              </div>
              <div>
                <label className="block text-xs text-slate-500 mb-1">Debt payoff (years)</label>
                <input
                  type="text"
                  value={regenDebtPayoff}
                  onChange={(e) => setRegenDebtPayoff(e.target.value)}
                  placeholder="optional"
                  className="border border-slate-200 rounded-lg px-3 py-1.5 text-sm w-28"
                />
              </div>
              <div>
                <label className="block text-xs text-slate-500 mb-1">Premium tolerance (0–1)</label>
                <input
                  type="text"
                  value={regenPremTol}
                  onChange={(e) => setRegenPremTol(e.target.value)}
                  placeholder="e.g. 0.08"
                  className="border border-slate-200 rounded-lg px-3 py-1.5 text-sm w-24"
                />
              </div>
              <button
                type="button"
                onClick={handleRegenerate}
                disabled={detailLoading}
                className="px-3 py-1.5 rounded-lg text-sm bg-slate-900 text-white disabled:opacity-50"
              >
                Regenerate
              </button>
            </div>
          </div>

          {detailLoading && (
            <div className="flex items-center gap-2 text-sm text-slate-500 py-8">
              <Loader2 size={16} className="animate-spin" />
              Loading dashboard…
            </div>
          )}
          {!detailLoading && detail?.dashboard_spec && (
            <DynamicInsuranceDashboardRenderer
              spec={detail.dashboard_spec}
              projectionData={detail.projection_data}
            />
          )}
        </div>
      )}
    </div>
  );
}
