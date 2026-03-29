'use client';

import { useEffect, useState, useCallback } from 'react';
import { Loader2, X, Sparkles, CheckCircle2, AlertTriangle, Info } from 'lucide-react';
import type { ObjectivesAutomationResult } from '../../lib/api';
import {
  OA_EVENT_START,
  OA_EVENT_DONE,
  describeAutomationResult,
} from '../../lib/objectives-automation-events';

type PanelState =
  | { kind: 'idle' }
  | { kind: 'running' }
  | { kind: 'finished'; result: ObjectivesAutomationResult };

export default function ObjectivesAutomationStatus({ clientId }: { clientId: string | null }) {
  const [state, setState] = useState<PanelState>({ kind: 'idle' });

  useEffect(() => {
    setState({ kind: 'idle' });
  }, [clientId]);

  useEffect(() => {
    if (!clientId) return;

    const onStart = (e: Event) => {
      const d = (e as CustomEvent<{ clientId?: string }>).detail;
      if (d?.clientId === clientId) setState({ kind: 'running' });
    };

    const onDone = (e: Event) => {
      const d = (e as CustomEvent<{ clientId?: string; result?: ObjectivesAutomationResult }>).detail;
      if (d?.clientId !== clientId || !d.result) return;
      setState({ kind: 'finished', result: d.result });
    };

    window.addEventListener(OA_EVENT_START, onStart);
    window.addEventListener(OA_EVENT_DONE, onDone);
    return () => {
      window.removeEventListener(OA_EVENT_START, onStart);
      window.removeEventListener(OA_EVENT_DONE, onDone);
    };
  }, [clientId]);

  const dismiss = useCallback(() => setState({ kind: 'idle' }), []);

  if (!clientId || state.kind === 'idle') return null;

  if (state.kind === 'running') {
    return (
      <div
        className="mb-4 rounded-xl border border-indigo-200 bg-indigo-50/90 px-4 py-3 shadow-sm"
        role="status"
        aria-live="polite"
        aria-busy="true"
      >
        <div className="flex items-start gap-3">
          <Loader2 className="h-5 w-5 text-indigo-600 flex-shrink-0 mt-0.5 animate-spin" aria-hidden />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold text-indigo-900 flex items-center gap-2">
              <Sparkles size={14} className="text-indigo-500" />
              Automated analysis in progress
            </p>
            <ul className="mt-2 text-xs text-indigo-800/90 space-y-1 list-disc list-inside">
              <li>Reading your Goals &amp; objectives and selecting insurance engines (LLM)</li>
              <li>Running calculations for each selected engine</li>
              <li>Writing one merged summary to Saved analyses</li>
            </ul>
            <p className="mt-2 text-xs text-indigo-600">This often takes 30–90 seconds. You can switch tabs; status stays here.</p>
          </div>
        </div>
      </div>
    );
  }

  const { tone, title, lines } = describeAutomationResult(state.result);
  const Icon =
    tone === 'success' ? CheckCircle2 : tone === 'warning' ? AlertTriangle : Info;
  const border =
    tone === 'success'
      ? 'border-emerald-200 bg-emerald-50/90'
      : tone === 'warning'
        ? 'border-amber-200 bg-amber-50/90'
        : 'border-slate-200 bg-slate-50/90';
  const iconColor =
    tone === 'success' ? 'text-emerald-600' : tone === 'warning' ? 'text-amber-600' : 'text-slate-500';

  return (
    <div
      className={`mb-4 rounded-xl border px-4 py-3 shadow-sm ${border}`}
      role="status"
      aria-live="polite"
    >
      <div className="flex items-start gap-3">
        <Icon className={`h-5 w-5 flex-shrink-0 mt-0.5 ${iconColor}`} aria-hidden />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-slate-900">{title}</p>
          <ul className="mt-1.5 text-xs text-slate-700 space-y-1">
            {lines.map((line, i) => (
              <li key={i}>{line}</li>
            ))}
          </ul>
        </div>
        <button
          type="button"
          onClick={dismiss}
          className="p-1 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-white/80 flex-shrink-0"
          aria-label="Dismiss"
        >
          <X size={16} />
        </button>
      </div>
    </div>
  );
}
