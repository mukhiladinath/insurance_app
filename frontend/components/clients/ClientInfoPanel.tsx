'use client';

import { useState, useEffect } from 'react';
import {
  User, DollarSign, Shield, Heart, FileText, ExternalLink, ClipboardList, Brain,
  ScrollText, GitCompare, LayoutDashboard,
} from 'lucide-react';
import type { ClientWorkspace, ConversationDocument } from '../../lib/types';
import { EMPTY_CLIENT_FACTS } from '../../lib/types';
import { formatTimestamp, parseUTCDate, formatFileSize } from '../../lib/utils';
import { getDocumentUrl } from '../../lib/api';
import FactFind from './FactFind';
import AIContextPanel from '../ai/AIContextPanel';
import SavedAnalysesPanel from './SavedAnalysesPanel';
import InsuranceComparisonPanel from './InsuranceComparisonPanel';
import InsuranceDashboardsPanel from './InsuranceDashboardsPanel';
import ObjectivesAutomationStatus from './ObjectivesAutomationStatus';
import type { PendingInsuranceComparison, PendingInsuranceDashboard } from '../../store/client-store';

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
// Tab definitions
// ---------------------------------------------------------------------------

type Tab = 'factfind' | 'personal' | 'financial' | 'insurance' | 'health' | 'documents' | 'saved-analyses' | 'compare' | 'dashboards' | 'ai-memory';

const TABS: { id: Tab; label: string; icon: React.ReactNode }[] = [
  { id: 'factfind',   label: 'Fact Find',  icon: <ClipboardList size={14} /> },
  { id: 'personal',   label: 'Personal',   icon: <User size={14} /> },
  { id: 'financial',  label: 'Financial',  icon: <DollarSign size={14} /> },
  { id: 'insurance',  label: 'Insurance',  icon: <Shield size={14} /> },
  { id: 'health',     label: 'Health',     icon: <Heart size={14} /> },
  { id: 'documents',  label: 'Documents',  icon: <FileText size={14} /> },
  { id: 'saved-analyses', label: 'Saved analyses', icon: <ScrollText size={14} /> },
  { id: 'compare',      label: 'Compare',      icon: <GitCompare size={14} /> },
  { id: 'dashboards',   label: 'Dashboards',   icon: <LayoutDashboard size={14} /> },
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
  preloadedInsuranceDashboard?: PendingInsuranceDashboard | null;
  onPreloadedDashboardConsumed?: () => void;
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
  preloadedInsuranceDashboard,
  onPreloadedDashboardConsumed,
  clientId,
}: Props) {
  const [activeTab, setActiveTab] = useState<Tab>(initialTab ?? 'factfind');

  // Jump to Compare / Dashboards when AI bar finished; otherwise honour initialTab (e.g. Fact Find).
  useEffect(() => {
    if (preloadedInsuranceDashboard) {
      setActiveTab('dashboards');
      return;
    }
    if (preloadedInsuranceComparison) {
      setActiveTab('compare');
      return;
    }
    if (initialTab) {
      setActiveTab(initialTab);
      if (initialTab !== 'compare' && initialTab !== 'dashboards') onTabConsumed?.();
    }
  }, [initialTab, preloadedInsuranceComparison, preloadedInsuranceDashboard, onTabConsumed]);

  const facts = workspace?.client_facts ?? EMPTY_CLIENT_FACTS;

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
        {activeTab === 'dashboards' && clientId && (
          <InsuranceDashboardsPanel
            clientId={clientId}
            preloaded={preloadedInsuranceDashboard ?? null}
            onPreloadedConsumed={onPreloadedDashboardConsumed}
          />
        )}
        {activeTab === 'dashboards' && !clientId && (
          <div className="text-sm text-slate-400 py-8 text-center">Save the client first to view dashboards.</div>
        )}
        {activeTab === 'ai-memory' && clientId && <AIContextPanel clientId={clientId} />}
        {activeTab === 'ai-memory' && !clientId && (
          <div className="text-sm text-slate-400 py-8 text-center">Save the client first to access AI Memory.</div>
        )}
      </div>
    </div>
  );
}
