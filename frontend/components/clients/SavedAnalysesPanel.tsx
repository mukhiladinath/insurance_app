'use client';

import { useState, useEffect, useCallback } from 'react';
import { Loader2, RefreshCw, Pencil, Save, X, Sparkles } from 'lucide-react';
import type { ClientAnalysisOutput, ClientAnalysisOutputsResponse } from '../../lib/types';
import MarkdownProse from '../ui/MarkdownProse';
import { formatTimestamp, parseUTCDate } from '../../lib/utils';

const BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

const TOOL_LABELS: Record<string, string> = {
  life_insurance_in_super: 'Life Insurance in Super',
  life_tpd_policy: 'Life & TPD Policy',
  income_protection_policy: 'Income Protection',
  ip_in_super: 'IP in Super',
  trauma_critical_illness: 'Trauma / CI',
  tpd_policy_assessment: 'TPD Assessment',
  tpd_in_super: 'TPD in Super',
  generate_soa: 'Generate SOA',
};

async function fetchOutputs(clientId: string): Promise<ClientAnalysisOutputsResponse> {
  const res = await fetch(`${BASE}/api/clients/${clientId}/analysis-outputs`);
  if (!res.ok) throw new Error(`Failed to load saved analyses (${res.status})`);
  return res.json();
}

async function patchOutput(clientId: string, outputId: string, content: string): Promise<ClientAnalysisOutput> {
  const res = await fetch(`${BASE}/api/clients/${clientId}/analysis-outputs/${outputId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err?.detail ?? `Save failed (${res.status})`);
  }
  return res.json();
}

function toolSummary(ids: string[]): string {
  return ids
    .map((id) => TOOL_LABELS[id] ?? id.replace(/_/g, ' '))
    .slice(0, 4)
    .join(' · ');
}

interface Props {
  clientId: string;
}

export default function SavedAnalysesPanel({ clientId }: Props) {
  const [outputs, setOutputs] = useState<ClientAnalysisOutput[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState('');
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchOutputs(clientId);
      setOutputs(data.outputs);
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
    const onChanged = (e: Event) => {
      const d = (e as CustomEvent<{ clientId?: string }>).detail;
      if (d?.clientId === clientId) load();
    };
    window.addEventListener('client-analysis-outputs-changed', onChanged);
    return () => window.removeEventListener('client-analysis-outputs-changed', onChanged);
  }, [clientId, load]);

  const startEdit = (o: ClientAnalysisOutput) => {
    setEditingId(o.id);
    setDraft(o.content);
    setExpandedId(o.id);
  };

  const cancelEdit = () => {
    setEditingId(null);
    setDraft('');
  };

  const saveEdit = async () => {
    if (!editingId) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await patchOutput(clientId, editingId, draft);
      setOutputs((prev) => prev.map((x) => (x.id === updated.id ? updated : x)));
      setEditingId(null);
      setDraft('');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
      <div className="px-5 py-3 bg-slate-50 border-b border-slate-100 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Sparkles size={15} className="text-indigo-500" />
          <h3 className="text-xs font-semibold text-slate-600 uppercase tracking-wider">Saved analyses</h3>
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

      {error && (
        <div className="px-5 py-2 bg-red-50 border-b border-red-100 text-xs text-red-700">{error}</div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-12 text-slate-400 gap-2">
          <Loader2 size={18} className="animate-spin" />
          <span className="text-sm">Loading…</span>
        </div>
      ) : outputs.length === 0 ? (
        <div className="p-8 text-center text-slate-500 text-sm">
          No saved analyses yet. Run an insurance analysis or SOA from the AI bar; the summary will appear here.
        </div>
      ) : (
        <ul className="divide-y divide-slate-100">
          {outputs.map((o) => {
            const open = expandedId === o.id;
            return (
              <li key={o.id} className="bg-white">
                <button
                  type="button"
                  onClick={() => setExpandedId(open ? null : o.id)}
                  className="w-full text-left px-5 py-3 hover:bg-slate-50/80 transition-colors"
                >
                  <p className="text-sm font-medium text-slate-800 line-clamp-2">{o.instruction || 'Analysis run'}</p>
                  <p className="text-xs text-slate-400 mt-1 flex flex-wrap items-center gap-1.5">
                    {formatTimestamp(parseUTCDate(o.created_at))}
                    {o.source === 'automated' && (
                      <span className="rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide bg-violet-100 text-violet-800 border border-violet-200">
                        Automated
                      </span>
                    )}
                    {o.tool_ids.length > 0 && (
                      <span className="text-slate-500"> · {toolSummary(o.tool_ids)}</span>
                    )}
                  </p>
                </button>
                {open && (
                  <div className="px-5 pb-4 border-t border-slate-50">
                    <div className="flex justify-end gap-2 py-2">
                      {editingId === o.id ? (
                        <>
                          <button
                            type="button"
                            onClick={cancelEdit}
                            disabled={saving}
                            className="inline-flex items-center gap-1 px-2.5 py-1 text-xs border border-slate-200 rounded-lg text-slate-600 hover:bg-slate-50"
                          >
                            <X size={12} /> Cancel
                          </button>
                          <button
                            type="button"
                            onClick={saveEdit}
                            disabled={saving}
                            className="inline-flex items-center gap-1 px-2.5 py-1 text-xs bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50"
                          >
                            {saving ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
                            Save
                          </button>
                        </>
                      ) : (
                        <button
                          type="button"
                          onClick={() => startEdit(o)}
                          className="inline-flex items-center gap-1 px-2.5 py-1 text-xs border border-slate-200 rounded-lg text-slate-600 hover:bg-slate-50"
                        >
                          <Pencil size={12} /> Edit
                        </button>
                      )}
                    </div>
                    {editingId === o.id ? (
                      <textarea
                        value={draft}
                        onChange={(e) => setDraft(e.target.value)}
                        className="w-full min-h-[220px] text-sm font-mono text-slate-800 border border-slate-200 rounded-lg p-3 focus:outline-none focus:ring-2 focus:ring-indigo-200"
                        spellCheck={false}
                      />
                    ) : (
                      <MarkdownProse content={o.content} />
                    )}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
