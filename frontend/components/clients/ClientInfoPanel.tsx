'use client';

import { useState, useEffect } from 'react';
import {
  User, DollarSign, Shield, Heart, Target, FileText, ExternalLink, TrendingUp, Clock, ClipboardList, Brain,
  ScrollText, GitCompare,
} from 'lucide-react';
import type { ClientWorkspace, ConversationDocument, AdvisoryNote } from '../../lib/types';
import { EMPTY_CLIENT_FACTS } from '../../lib/types';
import { formatTimestamp, parseUTCDate, formatFileSize } from '../../lib/utils';
import { getDocumentUrl } from '../../lib/api';
import FactFind from './FactFind';
import AIContextPanel from '../ai/AIContextPanel';
import SavedAnalysesPanel from './SavedAnalysesPanel';
import InsuranceComparisonPanel from './InsuranceComparisonPanel';
import ObjectivesAutomationStatus from './ObjectivesAutomationStatus';
import type { PendingInsuranceComparison } from '../../store/client-store';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (typeof value === 'number') {
    if (value >= 1000) return `$${value.toLocaleString()}`;
    return String(value);
  }
  if (Array.isArray(value)) return value.length > 0 ? value.join(', ') : '—';
  return String(value);
}

function FactRow({ label, value }: { label: string; value: unknown }) {
  const display = formatValue(value);
  return (
    <div className="py-3 border-b border-slate-100 last:border-0 flex items-start justify-between gap-4">
      <span className="text-sm text-slate-500 flex-shrink-0 w-48">{label}</span>
      <span className={`text-sm text-right ${display === '—' ? 'text-slate-300' : 'text-slate-900 font-medium'}`}>
        {display}
      </span>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
      <div className="px-5 py-3 bg-slate-50 border-b border-slate-100">
        <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider">{title}</h3>
      </div>
      <div className="px-5">{children}</div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Advisory verdict badge
// ---------------------------------------------------------------------------

function VerdictBadge({ verdict }: { verdict: string }) {
  const v = verdict.toUpperCase();
  const colors: Record<string, string> = {
    REPLACE: 'bg-orange-50 text-orange-700 border-orange-200',
    PURCHASE: 'bg-indigo-50 text-indigo-700 border-indigo-200',
    RETAIN: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    KEEP: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    PERMITTED: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    MUST_BE_SWITCHED_OFF: 'bg-red-50 text-red-700 border-red-200',
    NOT_RECOMMENDED: 'bg-red-50 text-red-700 border-red-200',
    COMPLETED: 'bg-slate-50 text-slate-600 border-slate-200',
    UNKNOWN: 'bg-slate-50 text-slate-400 border-slate-200',
  };
  const cls = colors[v] || 'bg-slate-50 text-slate-600 border-slate-200';
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold border ${cls}`}>
      {verdict}
    </span>
  );
}

const TOOL_LABELS: Record<string, string> = {
  purchase_retain_life_insurance_in_super: 'Life Insurance in Super',
  purchase_retain_life_tpd_policy: 'Life & TPD Policy',
  purchase_retain_income_protection_policy: 'Income Protection',
  purchase_retain_ip_in_super: 'Income Protection in Super',
  purchase_retain_trauma_ci_policy: 'Trauma / Critical Illness',
  tpd_policy_assessment: 'TPD Policy Assessment',
  purchase_retain_tpd_in_super: 'TPD in Super',
};

// ---------------------------------------------------------------------------
// Tab definitions
// ---------------------------------------------------------------------------

type Tab = 'factfind' | 'personal' | 'financial' | 'insurance' | 'health' | 'advisory' | 'documents' | 'saved-analyses' | 'compare' | 'ai-memory';

const TABS: { id: Tab; label: string; icon: React.ReactNode }[] = [
  { id: 'factfind',   label: 'Fact Find',  icon: <ClipboardList size={14} /> },
  { id: 'personal',   label: 'Personal',   icon: <User size={14} /> },
  { id: 'financial',  label: 'Financial',  icon: <DollarSign size={14} /> },
  { id: 'insurance',  label: 'Insurance',  icon: <Shield size={14} /> },
  { id: 'health',     label: 'Health',     icon: <Heart size={14} /> },
  { id: 'advisory',   label: 'Advisory',   icon: <TrendingUp size={14} /> },
  { id: 'documents',  label: 'Documents',  icon: <FileText size={14} /> },
  { id: 'saved-analyses', label: 'Saved analyses', icon: <ScrollText size={14} /> },
  { id: 'compare',      label: 'Compare',      icon: <GitCompare size={14} /> },
  { id: 'ai-memory',  label: 'AI Memory',  icon: <Brain size={14} /> },
];

// ---------------------------------------------------------------------------
// Tab content components
// ---------------------------------------------------------------------------

function PersonalTab({ facts }: { facts: Record<string, unknown> }) {
  const smoker = facts.is_smoker ?? facts.smoker_status;
  const fields = [
    ['Full Name',         facts.full_name],
    ['Age',               facts.age],
    ['Date of Birth',     facts.date_of_birth],
    ['Gender',            facts.gender],
    ['Marital Status',    facts.marital_status],
    ['Dependants',        facts.dependants],
    ['Occupation',        facts.occupation],
    ['Smoker',            smoker],
    ['State',             facts.state_of_residency],
  ];
  return (
    <Section title="Personal Details">
      {fields.map(([label, value]) => <FactRow key={label as string} label={label as string} value={value} />)}
    </Section>
  );
}

function FinancialTab({ facts }: { facts: Record<string, unknown> }) {
  const fields = [
    ['Annual Gross Income',    facts.annual_gross_income],
    ['Annual Net Income',      facts.annual_net_income],
    ['Monthly Expenses',       facts.monthly_expenses],
    ['Super Balance',          facts.super_balance],
    ['Fund Type',              facts.fund_type],
    ['Employer Contributions', facts.existing_contributions],
    ['Mortgage Balance',       facts.mortgage_balance],
    ['Total Liabilities',      facts.total_liabilities ?? facts.outstanding_debts],
    ['Monthly Surplus',        facts.monthly_surplus],
  ];
  return (
    <Section title="Financial Position">
      {fields.map(([label, value]) => <FactRow key={label as string} label={label as string} value={value} />)}
    </Section>
  );
}

function InsuranceTab({ facts }: { facts: Record<string, unknown> }) {
  const fields = [
    ['Has Existing Policy',     facts.has_existing_policy],
    ['Life Sum Insured',        facts.life_sum_insured],
    ['TPD Sum Insured',         facts.tpd_sum_insured],
    ['IP Monthly Benefit',      facts.ip_monthly_benefit ?? facts.ip_sum_insured],
    ['IP Waiting Period (weeks)', facts.ip_waiting_period_weeks],
    ['IP Waiting Period (days)', facts.ip_waiting_period_days],
    ['IP Benefit Period',       facts.ip_benefit_period_months ?? facts.ip_benefit_period],
    ['Annual Premium',          facts.annual_premium],
    ['Insurer Name',            facts.insurer_name ?? facts.current_insurer],
    ['Cover Types',             facts.cover_types ?? facts.policy_type],
  ];
  return (
    <Section title="Insurance Coverage">
      {fields.map(([label, value]) => <FactRow key={label as string} label={label as string} value={value} />)}
    </Section>
  );
}

function HealthTab({ facts }: { facts: Record<string, unknown> }) {
  const fields = [
    ['Medical Conditions',   facts.medical_conditions],
    ['Physical Impairments', facts.physical_impairments],
    ['Mental Health History',facts.mental_health_history],
    ['On Medication',        facts.on_medication],
  ];
  return (
    <Section title="Health Information">
      {fields.map(([label, value]) => <FactRow key={label as string} label={label as string} value={value} />)}
    </Section>
  );
}

function AdvisoryTab({ notes, summary }: { notes: Record<string, AdvisoryNote>; summary: string }) {
  const entries = Object.entries(notes);
  return (
    <div className="space-y-4">
      {summary && (
        <Section title="Conversation Summary">
          <p className="text-sm text-slate-700 py-3 leading-relaxed">{summary}</p>
        </Section>
      )}

      {entries.length === 0 && !summary && (
        <div className="bg-white rounded-xl border border-slate-200 p-8 text-center">
          <TrendingUp size={28} className="text-slate-300 mx-auto mb-3" />
          <p className="text-slate-500 text-sm">No analyses yet.</p>
          <p className="text-slate-400 text-xs mt-1">Run an analysis using the AI bar below.</p>
        </div>
      )}

      {entries.map(([toolName, note]) => (
        <div key={toolName} className="bg-white rounded-xl border border-slate-200 overflow-hidden">
          <div className="px-5 py-3 bg-slate-50 border-b border-slate-100 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-slate-700">
              {TOOL_LABELS[toolName] ?? toolName}
            </h3>
            <div className="flex items-center gap-2">
              <VerdictBadge verdict={note.verdict} />
              <span className="text-xs text-slate-400 flex items-center gap-1">
                <Clock size={10} />
                {note.analysed_at ? formatTimestamp(parseUTCDate(note.analysed_at)) : ''}
              </span>
            </div>
          </div>
          <div className="px-5 py-4">
            {note.recommendation && (
              <p className="text-sm font-medium text-slate-800 mb-2">{note.recommendation}</p>
            )}
            {note.key_findings && (
              <p className="text-sm text-slate-600 leading-relaxed">{note.key_findings}</p>
            )}
            {Object.keys(note.key_numbers ?? {}).length > 0 && (
              <div className="mt-3 flex flex-wrap gap-2">
                {Object.entries(note.key_numbers).map(([k, v]) => v != null && (
                  <span key={k} className="px-2 py-0.5 bg-slate-100 text-slate-700 rounded text-xs">
                    {k.replace(/_/g, ' ')}: <span className="font-semibold">{formatValue(v)}</span>
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

function DocumentsTab({ documents }: { documents: ConversationDocument[] }) {
  const iconColor: Record<string, string> = {
    'application/pdf': 'text-red-500',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'text-blue-500',
  };

  return (
    <div className="space-y-3">
      {documents.length === 0 && (
        <div className="bg-white rounded-xl border border-slate-200 p-8 text-center">
          <FileText size={28} className="text-slate-300 mx-auto mb-3" />
          <p className="text-slate-500 text-sm">No documents uploaded yet.</p>
        </div>
      )}
      {documents.map((doc) => (
        <div key={doc.id} className="bg-white rounded-xl border border-slate-200 p-4 flex items-start gap-3">
          <FileText size={18} className={`flex-shrink-0 mt-0.5 ${iconColor[doc.content_type] ?? 'text-slate-400'}`} />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-slate-800 truncate">{doc.filename}</p>
            <p className="text-xs text-slate-400">
              {formatFileSize(doc.size_bytes)} · {formatTimestamp(parseUTCDate(doc.created_at))}
            </p>
            {doc.facts_summary && (
              <p className="text-xs text-slate-500 mt-1 line-clamp-2">{doc.facts_summary}</p>
            )}
          </div>
          <a
            href={getDocumentUrl(doc.id)}
            target="_blank"
            rel="noreferrer"
            className="p-1.5 text-slate-400 hover:text-indigo-600 flex-shrink-0"
          >
            <ExternalLink size={14} />
          </a>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

interface Props {
  workspace: ClientWorkspace | null;
  documents: ConversationDocument[];
  initialTab?: Tab;
  factFindSection?: string;
  onTabConsumed?: () => void;
  preloadedInsuranceComparison?: PendingInsuranceComparison | null;
  onPreloadedComparisonConsumed?: () => void;
  clientId?: string | null;
}

export default function ClientInfoPanel({
  workspace,
  documents,
  initialTab,
  factFindSection,
  onTabConsumed,
  preloadedInsuranceComparison,
  onPreloadedComparisonConsumed,
  clientId,
}: Props) {
  const [activeTab, setActiveTab] = useState<Tab>(initialTab ?? 'factfind');

  // Jump to Compare when AI bar finished a compare run; otherwise honour initialTab (e.g. Fact Find).
  useEffect(() => {
    if (preloadedInsuranceComparison) {
      setActiveTab('compare');
      return;
    }
    if (initialTab) {
      setActiveTab(initialTab);
      if (initialTab !== 'compare') onTabConsumed?.();
    }
  }, [initialTab, preloadedInsuranceComparison, onTabConsumed]);

  const facts = workspace?.client_facts ?? EMPTY_CLIENT_FACTS;
  const advisoryNotes = workspace?.advisory_notes ?? {};

  return (
    <div className="flex-1 min-h-0 flex flex-col">
      {/* Tab bar */}
      <div className="flex gap-0.5 mb-5 bg-slate-100 rounded-lg p-1 w-fit">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
              activeTab === tab.id
                ? 'bg-white text-slate-900 shadow-sm'
                : 'text-slate-500 hover:text-slate-700'
            }`}
          >
            {tab.icon}
            {tab.label}
          </button>
        ))}
      </div>

      {clientId && <ObjectivesAutomationStatus clientId={clientId} />}

      {/* Tab content */}
      <div className="flex-1 overflow-y-auto">
        {activeTab === 'factfind'  && <FactFind clientFacts={facts} scrollToSection={factFindSection} />}
        {activeTab === 'personal'  && <PersonalTab facts={facts.personal} />}
        {activeTab === 'financial' && <FinancialTab facts={facts.financial} />}
        {activeTab === 'insurance' && <InsuranceTab facts={facts.insurance} />}
        {activeTab === 'health'    && <HealthTab facts={facts.health} />}
        {activeTab === 'advisory'  && <AdvisoryTab notes={advisoryNotes} summary={workspace?.summary ?? ''} />}
        {activeTab === 'documents' && <DocumentsTab documents={documents} />}
        {activeTab === 'saved-analyses' && clientId && <SavedAnalysesPanel clientId={clientId} />}
        {activeTab === 'saved-analyses' && !clientId && (
          <div className="text-sm text-slate-400 py-8 text-center">Save the client first to view saved analyses.</div>
        )}
        {activeTab === 'compare' && clientId && (
          <InsuranceComparisonPanel
            clientId={clientId}
            preloadedComparison={preloadedInsuranceComparison ?? null}
            onPreloadedComparisonConsumed={onPreloadedComparisonConsumed}
          />
        )}
        {activeTab === 'compare' && !clientId && (
          <div className="text-sm text-slate-400 py-8 text-center">Save the client first to compare tool outputs.</div>
        )}
        {activeTab === 'ai-memory' && clientId && <AIContextPanel clientId={clientId} />}
        {activeTab === 'ai-memory' && !clientId && (
          <div className="text-sm text-slate-400 py-8 text-center">Save the client first to access AI Memory.</div>
        )}
      </div>
    </div>
  );
}
