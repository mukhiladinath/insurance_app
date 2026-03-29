'use client';

import { useState } from 'react';
import {
  X, CheckCircle, XCircle, Loader2, Check, Ban,
  ChevronDown, ChevronRight, AlertCircle, Sparkles,
} from 'lucide-react';
import type {
  OrchestratorPhase,
  OrchestratorPlan,
  OrchestratorStepResult,
} from '../../lib/types';
import MarkdownProse from '../ui/MarkdownProse';

// ---------------------------------------------------------------------------
// Tool display names
// ---------------------------------------------------------------------------

const TOOL_LABELS: Record<string, string> = {
  get_client_factfind:       'Read Fact Find',
  update_client_factfind:    'Update Fact Find',
  get_client_profile:        'Read Client Profile',
  list_clients:              'List Clients',
  read_client_memory:        'Read AI Memory',
  search_client_memory:      'Search AI Memory',
  life_insurance_in_super:   'Life Insurance in Super',
  life_tpd_policy:           'Life & TPD Policy',
  income_protection_policy:  'Income Protection',
  ip_in_super:               'IP in Super',
  trauma_critical_illness:   'Trauma / CI',
  tpd_policy_assessment:     'TPD Assessment',
  tpd_in_super:              'TPD in Super',
  generate_soa:              'Generate SOA',
};

// ---------------------------------------------------------------------------
// Insurance tool result display — hides internal scores, shows advice
// ---------------------------------------------------------------------------

const INSURANCE_TOOL_IDS = new Set([
  'life_insurance_in_super',
  'life_tpd_policy',
  'income_protection_policy',
  'ip_in_super',
  'trauma_critical_illness',
  'tpd_policy_assessment',
  'tpd_in_super',
]);

const RECOMMENDATION_LABELS: Record<string, { label: string; color: string }> = {
  INSIDE_SUPER:             { label: 'Recommend: Inside Super',       color: 'bg-emerald-50 text-emerald-800 border-emerald-200' },
  OUTSIDE_SUPER:            { label: 'Recommend: Outside Super',      color: 'bg-blue-50 text-blue-800 border-blue-200' },
  SPLIT_STRATEGY:           { label: 'Recommend: Split Strategy',     color: 'bg-amber-50 text-amber-800 border-amber-200' },
  PURCHASE:                 { label: 'Recommend: Purchase',           color: 'bg-emerald-50 text-emerald-800 border-emerald-200' },
  RETAIN:                   { label: 'Recommend: Retain',             color: 'bg-emerald-50 text-emerald-800 border-emerald-200' },
  REPLACE:                  { label: 'Recommend: Replace',            color: 'bg-amber-50 text-amber-800 border-amber-200' },
  DO_NOT_REPLACE:           { label: 'Recommend: Do Not Replace',     color: 'bg-blue-50 text-blue-800 border-blue-200' },
  ALLOWED_AND_ACTIVE:       { label: 'Status: Allowed & Active',      color: 'bg-emerald-50 text-emerald-800 border-emerald-200' },
  ALLOWED_BUT_OPT_IN_REQUIRED: { label: 'Status: Opt-in Required',  color: 'bg-amber-50 text-amber-800 border-amber-200' },
  MUST_BE_SWITCHED_OFF:     { label: 'Status: Must Be Switched Off',  color: 'bg-red-50 text-red-800 border-red-200' },
  INSUFFICIENT_INFO:        { label: 'Status: Insufficient Info',     color: 'bg-slate-100 text-slate-600 border-slate-200' },
  NEEDS_MORE_INFO:          { label: 'Status: Needs More Info',       color: 'bg-slate-100 text-slate-600 border-slate-200' },
};

function StringList({ items, className }: { items: string[]; className?: string }) {
  if (!items?.length) return null;
  return (
    <ul className={`space-y-1 ${className ?? ''}`}>
      {items.map((item, i) => (
        <li key={i} className="flex gap-2 text-sm text-slate-700">
          <span className="text-indigo-400 flex-shrink-0 mt-0.5">•</span>
          <span>{item}</span>
        </li>
      ))}
    </ul>
  );
}

function RecommendationBadge({ value }: { value: string }) {
  const meta = RECOMMENDATION_LABELS[value];
  if (!meta) return <span className="text-sm font-semibold text-slate-700">{value.replace(/_/g, ' ')}</span>;
  return (
    <span className={`inline-block px-3 py-1 rounded-full text-sm font-semibold border ${meta.color}`}>
      {meta.label}
    </span>
  );
}

function InsuranceToolResult({ result }: { result: Record<string, unknown> }) {
  // Top-level recommendation (most tools)
  const placement = result.placement_assessment as Record<string, unknown> | undefined;
  const recommendation = (placement?.recommendation ?? result.recommendation) as string | undefined;
  const reasoning = (placement?.reasoning ?? result.reasoning) as string[] | undefined;
  const risks = (placement?.risks ?? result.risks) as string[] | undefined;

  // Legal status
  const legalStatus = result.legal_status as string | undefined;
  const legalReasons = result.legal_reasons as string[] | undefined;

  // Needs analysis
  const needsAnalysis = result.needs_analysis as Record<string, unknown> | undefined;
  const needsSummary = needsAnalysis?.recommendation_summary as string | undefined;

  // Member actions
  const memberActions = result.member_actions as string[] | undefined;

  // Advice narrative (some tools)
  const adviceSummary = result.advice_summary as string | undefined;

  return (
    <div className="space-y-3 pt-2">
      {/* Primary recommendation */}
      {recommendation && (
        <div>
          <RecommendationBadge value={recommendation} />
        </div>
      )}

      {/* Legal status (when no separate recommendation) */}
      {!recommendation && legalStatus && (
        <div>
          <RecommendationBadge value={legalStatus} />
        </div>
      )}

      {/* Reasoning */}
      {reasoning && reasoning.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">Reasoning</p>
          <StringList items={reasoning} />
        </div>
      )}

      {/* Legal reasons */}
      {legalReasons && legalReasons.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">Legal Basis</p>
          <StringList items={legalReasons} />
        </div>
      )}

      {/* Needs summary */}
      {needsSummary && (
        <div>
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">Coverage Needs</p>
          <p className="text-sm text-slate-700">{needsSummary}</p>
        </div>
      )}

      {/* Risks */}
      {risks && risks.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">Key Risks</p>
          <StringList items={risks} />
        </div>
      )}

      {/* Member actions */}
      {memberActions && memberActions.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">Required Actions</p>
          <StringList items={memberActions} />
        </div>
      )}

      {/* Advice summary narrative */}
      {adviceSummary && (
        <div>
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">Summary</p>
          <p className="text-sm text-slate-700 leading-relaxed">{adviceSummary}</p>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Step status badge
// ---------------------------------------------------------------------------

function StepRow({ result }: { result: OrchestratorStepResult }) {
  const [expanded, setExpanded] = useState(false);
  const toolLabel = TOOL_LABELS[result.tool_id] ?? result.tool_id.replace(/_/g, ' ');
  const hasData = result.result != null && (
    typeof result.result === 'object'
      ? Object.keys(result.result as object).length > 0
      : String(result.result).length > 0
  );

  return (
    <div className="border border-slate-100 rounded-lg overflow-hidden">
      <button
        onClick={() => hasData && setExpanded((v) => !v)}
        className="w-full flex items-center gap-3 px-3 py-2 text-left hover:bg-slate-50 transition-colors"
        disabled={!hasData}
      >
        {/* Status icon */}
        <span className="flex-shrink-0">
          {result.status === 'pending' && (
            <div className="w-4 h-4 rounded-full border-2 border-slate-300" />
          )}
          {result.status === 'running' && (
            <Loader2 size={16} className="text-indigo-500 animate-spin" />
          )}
          {result.status === 'completed' && (
            <CheckCircle size={16} className="text-emerald-500" />
          )}
          {result.status === 'failed' && (
            <XCircle size={16} className="text-red-500" />
          )}
        </span>

        {/* Label */}
        <span className={`text-sm font-medium flex-1 ${
          result.status === 'failed' ? 'text-red-600' : 'text-slate-700'
        }`}>
          {result.label || toolLabel}
        </span>

        {/* Tool name badge */}
        <span className="text-xs text-slate-400 font-mono hidden sm:block">{toolLabel}</span>

        {/* Duration */}
        {result.duration_ms && (
          <span className="text-xs text-slate-400">{result.duration_ms}ms</span>
        )}

        {/* Expand icon */}
        {hasData && (
          expanded
            ? <ChevronDown size={14} className="text-slate-400 flex-shrink-0" />
            : <ChevronRight size={14} className="text-slate-400 flex-shrink-0" />
        )}
      </button>

      {/* Error message */}
      {result.status === 'failed' && result.error && (
        <div className="px-3 pb-2 text-xs text-red-500">{result.error}</div>
      )}

      {/* Expanded result */}
      {expanded && result.result && (
        <div className="px-3 pb-3 border-t border-slate-100">
          {INSURANCE_TOOL_IDS.has(result.tool_id) && typeof result.result === 'object' ? (
            <InsuranceToolResult result={result.result as Record<string, unknown>} />
          ) : (
            <pre className="text-xs text-slate-500 bg-slate-50 rounded p-2 overflow-x-auto max-h-48 mt-2 whitespace-pre-wrap">
              {JSON.stringify(result.result, null, 2)}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Plan confirmation card
// ---------------------------------------------------------------------------

interface PlanCardProps {
  plan: OrchestratorPlan;
  onConfirm: () => void;
  onCancel: () => void;
}

function PlanCard({ plan, onConfirm, onCancel }: PlanCardProps) {
  return (
    <div className="px-4 py-3 bg-indigo-50 border-b border-indigo-100">
      {/* Explanation */}
      {plan.explanation && (
        <p className="text-sm text-indigo-900 mb-3">{plan.explanation}</p>
      )}

      {/* Numbered step labels */}
      <div className="space-y-1.5 mb-4">
        {plan.step_labels.map((label, i) => (
          <div key={i} className="flex items-center gap-2 text-sm text-indigo-800">
            <span className="w-5 h-5 rounded-full bg-indigo-200 text-indigo-700 text-xs flex items-center justify-center font-semibold flex-shrink-0">
              {i + 1}
            </span>
            {label}
          </div>
        ))}
      </div>

      {/* Confirm / Cancel buttons */}
      <div className="flex gap-2">
        <button
          onClick={onConfirm}
          className="flex items-center gap-1.5 px-4 py-1.5 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-700 transition-colors font-medium"
        >
          <Check size={14} /> Confirm
        </button>
        <button
          onClick={onCancel}
          className="flex items-center gap-1.5 px-4 py-1.5 bg-white border border-slate-200 text-slate-600 text-sm rounded-lg hover:bg-slate-50 transition-colors"
        >
          <Ban size={14} /> Cancel
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Clarification card
// ---------------------------------------------------------------------------

interface ClarificationCardProps {
  question: string;
  options: string[];
  onAnswer: (answer: string) => void;
}

function ClarificationCard({ question, options, onAnswer }: ClarificationCardProps) {
  const [input, setInput] = useState('');

  return (
    <div className="px-4 py-3 bg-amber-50 border-b border-amber-100">
      <div className="flex items-start gap-2 mb-2">
        <AlertCircle size={14} className="text-amber-500 flex-shrink-0 mt-0.5" />
        <p className="text-sm text-amber-900 font-medium">{question}</p>
      </div>

      {options.length > 0 && (
        <div className="flex gap-2 flex-wrap mb-2">
          {options.map((opt) => (
            <button
              key={opt}
              onClick={() => onAnswer(opt)}
              className="px-3 py-1 text-xs bg-white border border-amber-200 text-amber-700 rounded-full hover:bg-amber-50 transition-colors"
            >
              {opt}
            </button>
          ))}
        </div>
      )}

      <div className="flex gap-2">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && input.trim()) {
              onAnswer(input.trim());
              setInput('');
            }
          }}
          placeholder="Or type your answer…"
          className="flex-1 text-sm border border-amber-200 rounded-lg px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-amber-300 bg-white"
          autoFocus
        />
        <button
          onClick={() => { if (input.trim()) { onAnswer(input.trim()); setInput(''); } }}
          disabled={!input.trim()}
          className="px-3 py-1.5 bg-amber-500 text-white text-sm rounded-lg hover:bg-amber-600 disabled:opacity-40 transition-colors"
        >
          Submit
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main panel
// ---------------------------------------------------------------------------

interface Props {
  phase: OrchestratorPhase;
  plan: OrchestratorPlan | null;
  stepResults: OrchestratorStepResult[];
  synthesizedResponse: string;
  clarificationQuestion: string | null;
  clarificationOptions: string[];
  error: string | null;
  onConfirm: () => void;
  onCancel: () => void;
  onAnswerClarification: (answer: string) => void;
  onClose: () => void;
}

export default function AgentWorkspacePanel({
  phase,
  plan,
  stepResults,
  synthesizedResponse,
  clarificationQuestion,
  clarificationOptions,
  error,
  onConfirm,
  onCancel,
  onAnswerClarification,
  onClose,
}: Props) {
  const isRunning = phase === 'planning' || phase === 'executing';
  const isConfirming = phase === 'confirming';
  const isClarifying = phase === 'clarifying';
  const isComplete = phase === 'complete';
  const isError = phase === 'error';

  return (
    <div className="border-t border-slate-200 bg-white">
      {/* Panel header */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-slate-100">
        <div className="flex items-center gap-2">
          {isRunning && <Loader2 size={14} className="text-indigo-500 animate-spin" />}
          {isConfirming && <Sparkles size={14} className="text-indigo-500" />}
          {isClarifying && <AlertCircle size={14} className="text-amber-500" />}
          {isComplete && <div className="w-2 h-2 rounded-full bg-emerald-400" />}
          {isError && <div className="w-2 h-2 rounded-full bg-red-400" />}

          <span className="text-sm font-semibold text-slate-700">
            {isRunning && (phase === 'planning' ? 'Planning…' : 'Executing…')}
            {isConfirming && 'Confirm plan'}
            {isClarifying && 'Clarification needed'}
            {isComplete && 'Analysis complete'}
            {isError && 'Error'}
          </span>
        </div>
        <button
          onClick={onClose}
          className="p-1 text-slate-400 hover:text-slate-700 hover:bg-slate-100 rounded transition-colors"
        >
          <X size={14} />
        </button>
      </div>

      <div className="max-h-[28rem] overflow-y-auto">
        {/* Planning loading state */}
        {phase === 'planning' && (
          <div className="px-4 py-6 flex flex-col items-center gap-3">
            <div className="flex gap-2">
              {['Planning', 'Selecting tools', 'Preparing'].map((s, i) => (
                <div
                  key={s}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-slate-100 text-xs text-slate-500 animate-pulse"
                  style={{ animationDelay: `${i * 200}ms` }}
                >
                  <Loader2 size={10} className="animate-spin" />
                  {s}
                </div>
              ))}
            </div>
            <p className="text-xs text-slate-400">Analysing your instruction…</p>
          </div>
        )}

        {/* Plan confirmation */}
        {isConfirming && plan && (
          <PlanCard plan={plan} onConfirm={onConfirm} onCancel={onCancel} />
        )}

        {/* Clarification */}
        {isClarifying && clarificationQuestion && (
          <ClarificationCard
            question={clarificationQuestion}
            options={clarificationOptions}
            onAnswer={onAnswerClarification}
          />
        )}

        {/* Step results (shown during execution and after complete) */}
        {stepResults.length > 0 && (phase === 'executing' || isComplete || isError) && (
          <div className="px-4 pt-3 pb-2">
            <p className="text-xs text-slate-400 uppercase tracking-wide font-medium mb-2">Steps</p>
            <div className="space-y-1.5">
              {stepResults.map((r, i) => (
                <StepRow key={`${r.tool_id}-${i}`} result={r} />
              ))}
            </div>
          </div>
        )}

        {/* Synthesized response */}
        {isComplete && synthesizedResponse && (
          <div className="px-4 pt-2 pb-4 border-t border-slate-100">
            <p className="text-xs text-slate-400 uppercase tracking-wide font-medium mb-2">Summary</p>
            <MarkdownProse content={synthesizedResponse} />
          </div>
        )}

        {/* Error state */}
        {isError && error && (
          <div className="px-4 py-3">
            <div className="flex items-start gap-2 p-3 bg-red-50 border border-red-100 rounded-lg">
              <XCircle size={14} className="text-red-500 flex-shrink-0 mt-0.5" />
              <p className="text-sm text-red-700">{error}</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
