'use client';

import { useState, useCallback, useEffect } from 'react';
import { Save, Loader2, CheckCircle } from 'lucide-react';
import { useClientStore } from '../../store/client-store';
import { runObjectivesAutomation } from '../../lib/api';
import {
  dispatchObjectivesAutomationStart,
  dispatchObjectivesAutomationDone,
} from '../../lib/objectives-automation-events';
import type { ClientFacts } from '../../lib/types';

// ---------------------------------------------------------------------------
// Field definition types
// ---------------------------------------------------------------------------

type FieldType = 'text' | 'textarea' | 'number' | 'date' | 'boolean' | 'select' | 'tags';

interface FieldDef {
  key: string;
  label: string;
  type: FieldType;
  options?: { value: string; label: string }[];
  placeholder?: string;
  /** Rows for textarea fields */
  rows?: number;
}

interface SectionDef {
  id: keyof ClientFacts;
  title: string;
  fields: FieldDef[];
}

// ---------------------------------------------------------------------------
// Schema definition (mirrors memory_extractor.py canonical schema)
// ---------------------------------------------------------------------------

const SECTIONS: SectionDef[] = [
  {
    id: 'personal',
    title: 'Personal Details',
    fields: [
      { key: 'age', label: 'Age', type: 'number', placeholder: 'e.g. 35' },
      { key: 'date_of_birth', label: 'Date of Birth', type: 'date' },
      {
        key: 'gender', label: 'Gender', type: 'select',
        options: [
          { value: 'male', label: 'Male' },
          { value: 'female', label: 'Female' },
          { value: 'other', label: 'Other' },
        ],
      },
      {
        key: 'marital_status', label: 'Marital Status', type: 'select',
        options: [
          { value: 'single', label: 'Single' },
          { value: 'married', label: 'Married' },
          { value: 'de_facto', label: 'De Facto' },
          { value: 'divorced', label: 'Divorced' },
          { value: 'widowed', label: 'Widowed' },
        ],
      },
      { key: 'dependants', label: 'Number of Dependants', type: 'number', placeholder: '0' },
      { key: 'has_dependants', label: 'Has Dependants', type: 'boolean' },
      { key: 'occupation', label: 'Occupation', type: 'text', placeholder: 'e.g. Software Engineer' },
      {
        key: 'occupation_class', label: 'Occupation Class', type: 'select',
        options: [
          { value: 'CLASS_1_WHITE_COLLAR', label: 'Class 1 — White Collar' },
          { value: 'CLASS_2_LIGHT_BLUE', label: 'Class 2 — Light Blue Collar' },
          { value: 'CLASS_3_BLUE_COLLAR', label: 'Class 3 — Blue Collar' },
          { value: 'CLASS_4_HAZARDOUS', label: 'Class 4 — Hazardous' },
        ],
      },
      {
        key: 'employment_status', label: 'Employment Status', type: 'select',
        options: [
          { value: 'EMPLOYED_FULL_TIME', label: 'Employed Full Time' },
          { value: 'EMPLOYED_PART_TIME', label: 'Employed Part Time' },
          { value: 'SELF_EMPLOYED', label: 'Self Employed' },
          { value: 'UNEMPLOYED', label: 'Unemployed' },
        ],
      },
      { key: 'is_smoker', label: 'Smoker', type: 'boolean' },
      { key: 'weekly_hours_worked', label: 'Weekly Hours Worked', type: 'number', placeholder: 'e.g. 38' },
      { key: 'employment_ceased_date', label: 'Employment Ceased Date', type: 'date' },
    ],
  },
  {
    id: 'financial',
    title: 'Financial Position',
    fields: [
      { key: 'annual_gross_income', label: 'Annual Gross Income ($)', type: 'number', placeholder: 'e.g. 120000' },
      { key: 'annual_net_income', label: 'Annual Net Income ($)', type: 'number', placeholder: 'e.g. 88000' },
      { key: 'marginal_tax_rate', label: 'Marginal Tax Rate (0–1)', type: 'number', placeholder: 'e.g. 0.37' },
      { key: 'super_balance', label: 'Superannuation Balance ($)', type: 'number', placeholder: 'e.g. 150000' },
      {
        key: 'fund_type', label: 'Fund Type', type: 'select',
        options: [
          { value: 'mysuper', label: 'MySuper' },
          { value: 'choice', label: 'Choice' },
          { value: 'smsf', label: 'SMSF' },
          { value: 'defined_benefit', label: 'Defined Benefit' },
        ],
      },
      { key: 'fund_name', label: 'Fund Name', type: 'text', placeholder: 'e.g. Australian Super' },
      { key: 'is_mysuper', label: 'Is MySuper Fund', type: 'boolean' },
      { key: 'mortgage_balance', label: 'Mortgage Balance ($)', type: 'number', placeholder: 'e.g. 450000' },
      { key: 'liquid_assets', label: 'Liquid Assets ($)', type: 'number', placeholder: 'e.g. 30000' },
      { key: 'total_liabilities', label: 'Total Liabilities ($)', type: 'number', placeholder: 'e.g. 480000' },
      { key: 'monthly_expenses', label: 'Monthly Expenses ($)', type: 'number', placeholder: 'e.g. 4500' },
      { key: 'monthly_surplus', label: 'Monthly Surplus ($)', type: 'number', placeholder: 'e.g. 1500' },
      { key: 'years_to_retirement', label: 'Years to Retirement', type: 'number', placeholder: 'e.g. 25' },
      { key: 'received_contributions_last_16m', label: 'Received Contributions (last 16 months)', type: 'boolean' },
      { key: 'account_inactive_months', label: 'Account Inactive (months)', type: 'number', placeholder: 'e.g. 0' },
    ],
  },
  {
    id: 'insurance',
    title: 'Existing Insurance',
    fields: [
      { key: 'has_existing_policy', label: 'Has Existing Policy', type: 'boolean' },
      { key: 'insurer_name', label: 'Insurer Name', type: 'text', placeholder: 'e.g. AIA' },
      { key: 'annual_premium', label: 'Annual Premium ($)', type: 'number', placeholder: 'e.g. 2400' },
      { key: 'in_super', label: 'Cover Held in Super', type: 'boolean' },
      { key: 'life_sum_insured', label: 'Life Sum Insured ($)', type: 'number', placeholder: 'e.g. 1000000' },
      { key: 'tpd_sum_insured', label: 'TPD Sum Insured ($)', type: 'number', placeholder: 'e.g. 500000' },
      {
        key: 'tpd_definition', label: 'TPD Definition', type: 'select',
        options: [
          { value: 'OWN_OCCUPATION', label: 'Own Occupation' },
          { value: 'MODIFIED_OWN_OCCUPATION', label: 'Modified Own Occupation' },
          { value: 'ANY_OCCUPATION', label: 'Any Occupation' },
          { value: 'ACTIVITIES_OF_DAILY_LIVING', label: 'Activities of Daily Living' },
        ],
      },
      { key: 'ip_monthly_benefit', label: 'IP Monthly Benefit ($)', type: 'number', placeholder: 'e.g. 6000' },
      {
        key: 'ip_waiting_period_weeks', label: 'IP Waiting Period (weeks)', type: 'select',
        options: [2, 4, 8, 13, 26, 52].map((v) => ({ value: String(v), label: `${v} weeks` })),
      },
      {
        key: 'ip_waiting_period_days', label: 'IP Waiting Period (days)', type: 'select',
        options: [30, 60, 90].map((v) => ({ value: String(v), label: `${v} days` })),
      },
      {
        key: 'ip_benefit_period_months', label: 'IP Benefit Period', type: 'select',
        options: [
          { value: '0', label: 'To Age 65' },
          { value: '12', label: '12 months' },
          { value: '24', label: '24 months' },
          { value: '60', label: '5 years (60 months)' },
        ],
      },
      {
        key: 'ip_occupation_definition', label: 'IP Occupation Definition', type: 'select',
        options: [
          { value: 'OWN_OCCUPATION', label: 'Own Occupation' },
          { value: 'ANY_OCCUPATION', label: 'Any Occupation' },
          { value: 'ACTIVITIES_OF_DAILY_LIVING', label: 'Activities of Daily Living' },
        ],
      },
      { key: 'ip_has_step_down', label: 'IP Has Step-Down Benefit', type: 'boolean' },
      { key: 'ip_has_indexation', label: 'IP Has Indexation', type: 'boolean' },
      { key: 'ip_has_premium_waiver', label: 'IP Has Premium Waiver', type: 'boolean' },
      { key: 'ip_portability_available', label: 'IP Portability Available', type: 'boolean' },
      { key: 'ip_employer_sick_pay_weeks', label: 'Employer Sick Pay (weeks)', type: 'number', placeholder: 'e.g. 4' },
      { key: 'trauma_sum_insured', label: 'Trauma Sum Insured ($)', type: 'number', placeholder: 'e.g. 250000' },
      { key: 'trauma_waiting_period_days', label: 'Trauma Waiting Period (days)', type: 'number' },
      { key: 'trauma_survival_period_days', label: 'Trauma Survival Period (days)', type: 'number' },
      { key: 'trauma_has_advancement', label: 'Trauma Has Advancement Benefit', type: 'boolean' },
      { key: 'trauma_covered_conditions', label: 'Trauma Covered Conditions', type: 'tags' },
      { key: 'cover_types', label: 'Cover Types', type: 'tags' },
      { key: 'is_grandfathered', label: 'Is Grandfathered', type: 'boolean' },
      { key: 'policy_lapsed', label: 'Policy Lapsed', type: 'boolean' },
      { key: 'months_since_lapse', label: 'Months Since Lapse', type: 'number' },
      { key: 'policy_age_years', label: 'Policy Age (years)', type: 'number' },
      { key: 'opted_in_to_retain', label: 'Opted In to Retain', type: 'boolean' },
      { key: 'opted_out_of_insurance', label: 'Opted Out of Insurance', type: 'boolean' },
      { key: 'has_opted_in', label: 'Has Opted In', type: 'boolean' },
    ],
  },
  {
    id: 'health',
    title: 'Health Information',
    fields: [
      { key: 'height_cm', label: 'Height (cm)', type: 'number', placeholder: 'e.g. 175' },
      { key: 'height_m', label: 'Height (m)', type: 'number', placeholder: 'e.g. 1.75' },
      { key: 'weight_kg', label: 'Weight (kg)', type: 'number', placeholder: 'e.g. 80' },
      { key: 'medical_conditions', label: 'Medical Conditions', type: 'tags' },
      { key: 'current_medications', label: 'Current Medications', type: 'tags' },
      { key: 'hazardous_activities', label: 'Hazardous Activities', type: 'tags' },
    ],
  },
  {
    id: 'goals',
    title: 'Client Goals & Preferences',
    fields: [
      {
        key: 'goals_and_objectives',
        label: 'Goals & objectives (narrative)',
        type: 'textarea',
        rows: 5,
        placeholder:
          'Free text from the client file or interview: stated goals, objectives, priorities, time horizon, risk attitude, etc.',
      },
      { key: 'wants_replacement', label: 'Wants Policy Replacement', type: 'boolean' },
      { key: 'wants_retention', label: 'Wants to Retain Policy', type: 'boolean' },
      { key: 'affordability_is_concern', label: 'Affordability Is a Concern', type: 'boolean' },
      { key: 'wants_own_occupation', label: 'Wants Own Occupation Definition', type: 'boolean' },
      { key: 'wants_long_benefit_period', label: 'Wants Long Benefit Period', type: 'boolean' },
      { key: 'wants_indexation', label: 'Wants Indexation', type: 'boolean' },
      { key: 'cashflow_pressure', label: 'Under Cashflow Pressure', type: 'boolean' },
      { key: 'retirement_priority_high', label: 'Retirement a High Priority', type: 'boolean' },
      { key: 'contribution_cap_pressure', label: 'Near Contribution Cap', type: 'boolean' },
      { key: 'wants_advancement_benefit', label: 'Wants Advancement Benefit', type: 'boolean' },
      { key: 'wants_multi_claim_rider', label: 'Wants Multi-Claim Rider', type: 'boolean' },
    ],
  },
];

// ---------------------------------------------------------------------------
// Local state type: section → field → string (all values as strings in form)
// ---------------------------------------------------------------------------

type FormState = Record<string, Record<string, string>>;

function initFormState(clientFacts: ClientFacts): FormState {
  const state: FormState = {};
  for (const section of SECTIONS) {
    state[section.id] = {};
    const sectionData = (clientFacts as Record<string, Record<string, unknown>>)[section.id] ?? {};
    for (const field of section.fields) {
      const val = sectionData[field.key];
      if (val === undefined || val === null) {
        state[section.id][field.key] = '';
      } else if (Array.isArray(val)) {
        state[section.id][field.key] = val.join(', ');
      } else {
        state[section.id][field.key] = String(val);
      }
    }
  }
  return state;
}

function castValue(value: string, type: FieldType): unknown {
  if (value === '' || value === null) return null;
  switch (type) {
    case 'number':
      return value === '' ? null : Number(value);
    case 'boolean':
      return value === 'true';
    case 'tags':
      return value.split(',').map((s) => s.trim()).filter(Boolean);
    case 'textarea':
      return value.trim() === '' ? null : value.trim();
    default:
      return value || null;
  }
}

function buildPatch(form: FormState): Record<string, Record<string, unknown>> {
  const patch: Record<string, Record<string, unknown>> = {};
  for (const section of SECTIONS) {
    patch[section.id] = {};
    for (const field of section.fields) {
      const raw = form[section.id]?.[field.key] ?? '';
      patch[section.id][field.key] = castValue(raw, field.type);
    }
  }
  return patch;
}

// ---------------------------------------------------------------------------
// Field input components
// ---------------------------------------------------------------------------

function FieldInput({
  field,
  value,
  onChange,
}: {
  field: FieldDef;
  value: string;
  onChange: (v: string) => void;
}) {
  const base = 'w-full text-sm border border-slate-200 rounded-lg px-3 py-1.5 bg-white text-slate-900 focus:outline-none focus:ring-2 focus:ring-indigo-300 focus:border-indigo-400 placeholder-slate-300';

  if (field.type === 'boolean') {
    return (
      <select value={value} onChange={(e) => onChange(e.target.value)} className={base}>
        <option value="">—</option>
        <option value="true">Yes</option>
        <option value="false">No</option>
      </select>
    );
  }

  if (field.type === 'select' && field.options) {
    return (
      <select value={value} onChange={(e) => onChange(e.target.value)} className={base}>
        <option value="">—</option>
        {field.options.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    );
  }

  if (field.type === 'tags') {
    return (
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Comma-separated values"
        className={base}
      />
    );
  }

  if (field.type === 'date') {
    return (
      <input
        type="date"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={base}
      />
    );
  }

  if (field.type === 'text') {
    return (
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={field.placeholder}
        className={base}
      />
    );
  }

  if (field.type === 'textarea') {
    return (
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={field.placeholder}
        rows={field.rows ?? 4}
        className={`${base} min-h-[96px] resize-y`}
      />
    );
  }

  // number (default)
  return (
    <input
      type="number"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={field.placeholder}
      className={base}
      step={field.key.includes('rate') || field.key.includes('height_m') ? '0.01' : '1'}
    />
  );
}

// ---------------------------------------------------------------------------
// Section form
// ---------------------------------------------------------------------------

function SectionForm({
  section,
  values,
  onChange,
}: {
  section: SectionDef;
  values: Record<string, string>;
  onChange: (field: string, value: string) => void;
}) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 overflow-hidden mb-4">
      <div className="px-5 py-3 bg-slate-50 border-b border-slate-100">
        <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider">{section.title}</h3>
      </div>
      <div className="px-5 py-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
        {section.fields.map((field) => (
          <div key={field.key} className={field.type === 'textarea' ? 'sm:col-span-2' : undefined}>
            <label className="block text-xs text-slate-400 mb-1">{field.label}</label>
            <FieldInput
              field={field}
              value={values[field.key] ?? ''}
              onChange={(v) => onChange(field.key, v)}
            />
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main FactFind component
// ---------------------------------------------------------------------------

interface Props {
  clientFacts: ClientFacts;
  scrollToSection?: string;
}

export default function FactFind({ clientFacts, scrollToSection }: Props) {
  const { activeClientId, updateFacts } = useClientStore();
  const [form, setForm] = useState<FormState>(() => initFormState(clientFacts));
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  // Re-sync when saved factfind content changes (reference alone is unreliable if parent used inline `{}` fallbacks).
  const clientFactsKey = JSON.stringify(clientFacts);
  useEffect(() => {
    setForm(initFormState(clientFacts));
    // Same content must not re-run when parent passes a new object reference; key is the source of truth.
    // eslint-disable-next-line react-hooks/exhaustive-deps -- clientFacts aligns with clientFactsKey on this render
  }, [clientFactsKey]);

  // Auto-scroll to a section when directed from Context Panel
  useEffect(() => {
    if (!scrollToSection) return;
    const el = document.getElementById(`factfind-section-${scrollToSection}`);
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, [scrollToSection]);

  const handleChange = useCallback((section: string, field: string, value: string) => {
    setForm((prev) => ({
      ...prev,
      [section]: { ...prev[section], [field]: value },
    }));
    setSaved(false);
    setSaveError(null);
  }, []);

  const handleSave = async () => {
    if (!activeClientId || saving) return;
    setSaving(true);
    setSaveError(null);
    try {
      const patch = buildPatch(form);
      await updateFacts(activeClientId, patch);
      const objRaw = patch.goals?.goals_and_objectives;
      const objectivesText =
        typeof objRaw === 'string' ? objRaw.trim() : objRaw != null ? String(objRaw).trim() : '';
      if (objectivesText.length > 0) {
        dispatchObjectivesAutomationStart(activeClientId);
        try {
          const autoResult = await runObjectivesAutomation(activeClientId);
          dispatchObjectivesAutomationDone(activeClientId, autoResult);
          if (typeof window !== 'undefined') {
            window.dispatchEvent(
              new CustomEvent('client-analysis-outputs-changed', { detail: { clientId: activeClientId } }),
            );
            if (autoResult.insurance_dashboard_id) {
              window.dispatchEvent(
                new CustomEvent('insurance-dashboard-created', {
                  detail: { clientId: activeClientId, dashboardId: autoResult.insurance_dashboard_id },
                }),
              );
              useClientStore.getState().requestInsuranceDashboardView({
                clientId: activeClientId,
                dashboardId: autoResult.insurance_dashboard_id,
              });
            }
          }
        } catch (autoErr) {
          console.error('Goals-based automation failed:', autoErr);
          dispatchObjectivesAutomationDone(activeClientId, {
            skipped: false,
            reason:
              autoErr instanceof Error ? autoErr.message : 'Automated analysis failed. Try again later.',
            tools_run: [],
            outputs_created: 0,
          });
        }
      }
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Save failed';
      setSaveError(msg);
      console.error('FactFind save failed:', err);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex flex-col gap-1">
      {/* Header with save button */}
      <div className="flex items-center justify-between mb-4">
        <p className="text-xs text-slate-400 leading-relaxed">
          Enter client information gathered during the fact find interview. Fields left blank are ignored.
          When you save non-empty{' '}
          <span className="font-medium text-slate-500">Goals &amp; objectives</span>, an LLM picks relevant
          insurance engines, runs them, saves one merged write-up under Saved analyses (tagged Automated), and
          tries to create an insurance projection dashboard on the Dashboards tab when enough fields are
          available.
        </p>
        <button
          onClick={handleSave}
          disabled={!activeClientId || saving}
          className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition-colors flex-shrink-0 ml-4 ${
            saved
              ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
              : 'bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed'
          }`}
        >
          {saving ? (
            <Loader2 size={14} className="animate-spin" />
          ) : saved ? (
            <CheckCircle size={14} />
          ) : (
            <Save size={14} />
          )}
          {saving ? 'Saving…' : saved ? 'Saved' : 'Save'}
        </button>
      </div>

      {saveError && (
        <div className="mb-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
          {saveError}
        </div>
      )}

      {SECTIONS.map((section) => (
        <div key={section.id} id={`factfind-section-${section.id}`}>
          <SectionForm
            section={section}
            values={form[section.id] ?? {}}
            onChange={(field, value) => handleChange(section.id, field, value)}
          />
        </div>
      ))}
    </div>
  );
}
