'use client';

import { useState } from 'react';
import {
  Brain, User, DollarSign, Shield, Heart, Target,
  CheckCircle, AlertCircle, ChevronDown, ChevronUp, ClipboardList,
} from 'lucide-react';
import type { ClientWorkspace } from '../../lib/types';
import { EMPTY_CLIENT_FACTS } from '../../lib/types';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const SECTION_META: Record<string, { label: string; icon: React.ReactNode; color: string }> = {
  personal:  { label: 'Personal',  icon: <User size={12} />,       color: 'text-blue-600' },
  financial: { label: 'Financial', icon: <DollarSign size={12} />, color: 'text-green-600' },
  insurance: { label: 'Insurance', icon: <Shield size={12} />,     color: 'text-indigo-600' },
  health:    { label: 'Health',    icon: <Heart size={12} />,      color: 'text-red-500' },
  goals:     { label: 'Goals',     icon: <Target size={12} />,     color: 'text-amber-600' },
};

const ALL_SECTIONS = ['personal', 'financial', 'insurance', 'health', 'goals'];

// Fields considered "critical" for most insurance analyses
const CRITICAL_FIELDS: Record<string, string[]> = {
  personal:  ['age', 'occupation', 'employment_status', 'is_smoker', 'dependants'],
  financial: ['annual_gross_income', 'super_balance', 'mortgage_balance', 'monthly_expenses'],
  insurance: ['has_existing_policy', 'life_sum_insured', 'tpd_sum_insured', 'ip_monthly_benefit'],
  health:    ['medical_conditions'],
  goals:     [],
};

function fieldLabel(field: string): string {
  return field.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

// ---------------------------------------------------------------------------
// Section completeness row
// ---------------------------------------------------------------------------

function SectionRow({
  section,
  loadedFields,
  allFactsForSection,
  onOpenFactFind,
}: {
  section: string;
  loadedFields: string[];   // fields with non-null values (from last run context)
  allFactsForSection: Record<string, unknown>;  // from workspace
  onOpenFactFind: (section: string) => void;
}) {
  const meta = SECTION_META[section] ?? { label: section, icon: null, color: 'text-slate-600' };
  const critical = CRITICAL_FIELDS[section] ?? [];

  // Use workspace facts to check completeness (more accurate than run snapshot)
  const filled = Object.entries(allFactsForSection)
    .filter(([, v]) => v !== null && v !== undefined && v !== '' && !(Array.isArray(v) && v.length === 0))
    .map(([k]) => k);

  const missingCritical = critical.filter((f) => !filled.includes(f));
  const hasCriticalMissing = missingCritical.length > 0;
  const hasAnyData = filled.length > 0;

  return (
    <div className="flex items-center gap-2 py-1.5">
      <div className={`${meta.color} flex-shrink-0`}>{meta.icon}</div>
      <span className="text-xs text-slate-600 w-16 flex-shrink-0">{meta.label}</span>
      <div className="flex-1 flex items-center gap-1 flex-wrap">
        {!hasAnyData ? (
          <span className="text-xs text-slate-300 italic">empty</span>
        ) : (
          <span className="text-xs text-emerald-600 font-medium">{filled.length} field{filled.length !== 1 ? 's' : ''}</span>
        )}
        {hasCriticalMissing && (
          <span className="text-xs text-amber-600">
            · missing: {missingCritical.map(fieldLabel).join(', ')}
          </span>
        )}
      </div>
      {(!hasAnyData || hasCriticalMissing) && (
        <button
          onClick={() => onOpenFactFind(section)}
          className="text-xs text-indigo-500 hover:text-indigo-700 flex-shrink-0 underline underline-offset-2"
        >
          Fill in
        </button>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Missing fields alert (shown when clarification_needed)
// ---------------------------------------------------------------------------

export function MissingFieldsAlert({
  missingContext,
  clarificationQuestion,
  onOpenFactFind,
}: {
  missingContext: string[];
  clarificationQuestion: string | null;
  onOpenFactFind: (section: string) => void;
}) {
  if (!missingContext.length && !clarificationQuestion) return null;

  // Group missing fields by section
  const bySection: Record<string, string[]> = {};
  for (const path of missingContext) {
    const [section, ...rest] = path.split('.');
    if (!bySection[section]) bySection[section] = [];
    bySection[section].push(rest.join('.'));
  }

  return (
    <div className="mx-4 my-3 bg-amber-50 border border-amber-200 rounded-lg p-3">
      <div className="flex items-start gap-2 mb-2">
        <AlertCircle size={15} className="text-amber-500 flex-shrink-0 mt-0.5" />
        <p className="text-sm text-amber-800 leading-snug">
          {clarificationQuestion || 'Some required information is missing to complete this analysis.'}
        </p>
      </div>

      {Object.entries(bySection).length > 0 && (
        <div className="mt-2 space-y-1.5 pl-5">
          {Object.entries(bySection).map(([section, fields]) => {
            const meta = SECTION_META[section];
            return (
              <div key={section} className="flex items-center gap-2">
                <span className={`${meta?.color ?? 'text-slate-500'} flex items-center gap-1 text-xs font-medium min-w-[80px]`}>
                  {meta?.icon}
                  {meta?.label ?? section}
                </span>
                <span className="text-xs text-amber-700 flex-1">
                  {fields.map(fieldLabel).join(', ')}
                </span>
                <button
                  onClick={() => onOpenFactFind(section)}
                  className="text-xs text-indigo-600 hover:text-indigo-800 font-medium underline underline-offset-2 flex-shrink-0"
                >
                  Fill in →
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main context panel (shown in client profile)
// ---------------------------------------------------------------------------

interface Props {
  workspace: ClientWorkspace | null;
  onOpenFactFind: (section?: string) => void;
}

export default function ContextPanel({ workspace, onOpenFactFind }: Props) {
  const [expanded, setExpanded] = useState(false);

  const facts = workspace?.client_facts ?? EMPTY_CLIENT_FACTS;

  // Count total filled fields across all sections
  const totalFilled = ALL_SECTIONS.reduce((acc, s) => {
    const sec = (facts as Record<string, Record<string, unknown>>)[s] ?? {};
    return acc + Object.values(sec).filter((v) => v !== null && v !== undefined && v !== '' && !(Array.isArray(v) && v.length === 0)).length;
  }, 0);

  const advisoryCount = Object.keys(workspace?.advisory_notes ?? {}).length;

  // Determine overall readiness
  const allCritical = ALL_SECTIONS.flatMap((s) => CRITICAL_FIELDS[s] ?? []);
  const allFilledKeys = ALL_SECTIONS.flatMap((s) =>
    Object.entries((facts as Record<string, Record<string, unknown>>)[s] ?? {})
      .filter(([, v]) => v !== null && v !== undefined && v !== '' && !(Array.isArray(v) && v.length === 0))
      .map(([k]) => k)
  );
  const missingCriticalCount = allCritical.filter((f) => !allFilledKeys.includes(f)).length;

  return (
    <div className="bg-white border border-slate-200 rounded-xl overflow-hidden mb-4">
      {/* Header */}
      <button
        onClick={() => setExpanded((p) => !p)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-slate-50 transition-colors"
      >
        <div className="flex items-center gap-2">
          <Brain size={14} className="text-indigo-500" />
          <span className="text-sm font-semibold text-slate-700">Agent Context</span>
          <div className="flex items-center gap-1.5 ml-2">
            <span className="px-2 py-0.5 bg-indigo-50 text-indigo-700 text-xs rounded-full font-medium">
              {totalFilled} fields
            </span>
            {advisoryCount > 0 && (
              <span className="px-2 py-0.5 bg-emerald-50 text-emerald-700 text-xs rounded-full font-medium">
                {advisoryCount} analys{advisoryCount === 1 ? 'is' : 'es'}
              </span>
            )}
            {missingCriticalCount > 0 ? (
              <span className="px-2 py-0.5 bg-amber-50 text-amber-700 text-xs rounded-full font-medium flex items-center gap-1">
                <AlertCircle size={10} />
                {missingCriticalCount} critical missing
              </span>
            ) : totalFilled > 0 ? (
              <span className="px-2 py-0.5 bg-emerald-50 text-emerald-700 text-xs rounded-full font-medium flex items-center gap-1">
                <CheckCircle size={10} />
                Ready
              </span>
            ) : null}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {expanded ? <ChevronUp size={14} className="text-slate-400" /> : <ChevronDown size={14} className="text-slate-400" />}
        </div>
      </button>

      {/* Expanded content */}
      {expanded && (
        <div className="border-t border-slate-100 px-4 py-3">
          {/* Per-section breakdown */}
          <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2">Data by Section</p>
          <div className="divide-y divide-slate-50">
            {ALL_SECTIONS.map((section) => (
              <SectionRow
                key={section}
                section={section}
                loadedFields={[]}
                allFactsForSection={(facts as Record<string, Record<string, unknown>>)[section] ?? {}}
                onOpenFactFind={onOpenFactFind}
              />
            ))}
          </div>

          {/* Quick fill button */}
          {missingCriticalCount > 0 && (
            <button
              onClick={() => onOpenFactFind()}
              className="mt-3 w-full flex items-center justify-center gap-1.5 px-3 py-2 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 text-xs font-medium rounded-lg transition-colors"
            >
              <ClipboardList size={12} />
              Open Fact Find to fill in missing fields
            </button>
          )}
        </div>
      )}
    </div>
  );
}
