'use client';

import type { DataCard as DataCardType } from '../../lib/types';

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (typeof value === 'number') {
    if (value >= 1000) return `$${value.toLocaleString()}`;
    return String(value);
  }
  if (Array.isArray(value)) return value.join(', ') || '—';
  return String(value);
}

const VERDICT_STYLES: Record<string, string> = {
  REPLACE:              'bg-orange-50 text-orange-700 border-orange-200',
  PURCHASE:             'bg-indigo-50 text-indigo-700 border-indigo-200',
  RETAIN:               'bg-emerald-50 text-emerald-700 border-emerald-200',
  KEEP:                 'bg-emerald-50 text-emerald-700 border-emerald-200',
  PERMITTED:            'bg-emerald-50 text-emerald-700 border-emerald-200',
  PERMITTED_WITH_ELECTIONS: 'bg-amber-50 text-amber-700 border-amber-200',
  MUST_BE_SWITCHED_OFF: 'bg-red-50 text-red-700 border-red-200',
  NOT_RECOMMENDED:      'bg-red-50 text-red-700 border-red-200',
  COMPLETED:            'bg-slate-50 text-slate-600 border-slate-200',
};

function VerdictBadge({ text }: { text: string }) {
  const cls = VERDICT_STYLES[text?.toUpperCase?.()] ?? 'bg-slate-50 text-slate-600 border-slate-200';
  return (
    <span className={`inline-flex items-center px-2.5 py-1 rounded-lg text-xs font-bold border ${cls}`}>
      {text}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Recommendation card (life_tpd, ip, trauma)
// ---------------------------------------------------------------------------

function RecommendationCard({ data }: { data: Record<string, unknown> }) {
  const rec = (data.recommendation ?? {}) as Record<string, unknown>;
  const verdict = (rec.type ?? data.verdict ?? data.adequacy_verdict ?? '') as string;
  const summary = (rec.summary ?? rec.rationale ?? '') as string;

  const keyNums: [string, unknown][] = [
    ['Life sum insured', (data.life_need as any)?.recommended_sum ?? data.recommended_life_sum ?? null],
    ['TPD sum insured',  (data.tpd_need as any)?.recommended_sum ?? data.recommended_tpd_sum ?? null],
    ['Monthly benefit',  data.monthly_benefit_need ?? null],
    ['Replacement ratio', data.replacement_ratio ? `${Math.round((data.replacement_ratio as number) * 100)}%` : null],
    ['Recommended sum',  data.recommended_sum_insured ?? null],
  ].filter(([, v]) => v != null) as [string, unknown][];

  return (
    <div>
      <div className="flex items-center gap-2 mb-3">
        {verdict && <VerdictBadge text={verdict} />}
      </div>
      {summary && <p className="text-sm text-slate-600 leading-relaxed mb-3">{summary}</p>}
      {keyNums.length > 0 && (
        <div className="grid grid-cols-2 gap-2">
          {keyNums.map(([label, value]) => (
            <div key={label} className="bg-slate-50 rounded-lg px-3 py-2">
              <p className="text-xs text-slate-400">{label}</p>
              <p className="text-sm font-semibold text-slate-800">{formatValue(value)}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Summary with actions (life_in_super, tpd_in_super, ip_in_super)
// ---------------------------------------------------------------------------

function SummaryWithActionsCard({ data }: { data: Record<string, unknown> }) {
  const legalStatus = (data.legal_status ?? '') as string;
  const placement = (data.placement_assessment as any)?.recommendation ?? '';
  const actions = (data.member_actions as any[]) ?? [];
  const highPriority = actions.filter((a) => a.priority === 'HIGH');

  return (
    <div>
      <div className="flex items-center gap-2 mb-3 flex-wrap">
        {legalStatus && <VerdictBadge text={legalStatus} />}
        {placement && (
          <span className="text-xs text-slate-500 bg-slate-100 px-2 py-0.5 rounded">
            {placement.replace(/_/g, ' ')}
          </span>
        )}
      </div>
      {highPriority.length > 0 && (
        <div className="space-y-1.5">
          <p className="text-xs font-medium text-slate-500 uppercase tracking-wide">Required Actions</p>
          {highPriority.slice(0, 3).map((a: any, i: number) => (
            <div key={i} className="flex gap-2 text-sm">
              <span className="text-red-400 flex-shrink-0 mt-0.5">•</span>
              <span className="text-slate-700">{a.action}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Gap analysis card (tpd_assessment)
// ---------------------------------------------------------------------------

function GapAnalysisCard({ data }: { data: Record<string, unknown> }) {
  const verdict = (data.adequacy_verdict ?? '') as string;
  const gap = (data.gap_analysis as any) ?? {};
  const shortfall = gap.shortfall ?? null;
  const recommendation = (data.recommendation ?? '') as string;

  return (
    <div>
      <div className="flex items-center gap-2 mb-3">
        {verdict && <VerdictBadge text={verdict} />}
      </div>
      {shortfall != null && (
        <div className="bg-orange-50 border border-orange-100 rounded-lg px-3 py-2 mb-3">
          <p className="text-xs text-orange-600">Coverage Gap</p>
          <p className="text-lg font-bold text-orange-700">{formatValue(shortfall)}</p>
        </div>
      )}
      {recommendation && (
        <p className="text-sm text-slate-600 leading-relaxed">{recommendation}</p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Generic fallback
// ---------------------------------------------------------------------------

function GenericCard({ data }: { data: Record<string, unknown> }) {
  const entries = Object.entries(data)
    .filter(([, v]) => v != null && typeof v !== 'object')
    .slice(0, 6);

  return (
    <div className="space-y-1.5">
      {entries.map(([k, v]) => (
        <div key={k} className="flex justify-between text-sm">
          <span className="text-slate-400">{k.replace(/_/g, ' ')}</span>
          <span className="font-medium text-slate-700">{formatValue(v)}</span>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main DataCard component
// ---------------------------------------------------------------------------

export default function DataCard({ card }: { card: DataCardType }) {
  const borderColors: Record<string, string> = {
    recommendation_card:     'border-l-indigo-400',
    summary_with_actions:    'border-l-emerald-400',
    gap_analysis_card:       'border-l-orange-400',
    table:                   'border-l-slate-300',
  };
  const border = borderColors[card.display_hint] ?? 'border-l-slate-300';

  return (
    <div className={`bg-white border border-slate-200 border-l-4 ${border} rounded-xl p-4 min-w-[260px] max-w-[320px] flex-shrink-0`}>
      <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">{card.title}</p>

      {card.display_hint === 'recommendation_card'  && <RecommendationCard data={card.data} />}
      {card.display_hint === 'summary_with_actions' && <SummaryWithActionsCard data={card.data} />}
      {card.display_hint === 'gap_analysis_card'    && <GapAnalysisCard data={card.data} />}
      {card.display_hint === 'table'                && <GenericCard data={card.data} />}
      {!['recommendation_card','summary_with_actions','gap_analysis_card','table'].includes(card.display_hint) && (
        <GenericCard data={card.data} />
      )}
    </div>
  );
}
