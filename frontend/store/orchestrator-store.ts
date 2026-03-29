/**
 * orchestrator-store.ts — Zustand store for the finobi-style AI orchestrator.
 *
 * Phase machine:
 *   idle → planning → confirming → executing → complete
 *                  ↘ clarifying ↗   (regular LLM clarification or missing-field pause)
 *                  ↘ error
 *
 * Missing-field pause/resume:
 *   When an insurance tool detects a missing critical field, execution pauses
 *   (phase → 'clarifying', missingFieldMode = true). The user provides the value
 *   via the AIBar, which calls answerClarification(). Once all fields are collected
 *   the store calls _resumeExecution() which re-POSTs to /api/orchestrator/confirm
 *   with resume_from_index and the overrides injected into the paused step's params.
 */

import { create } from 'zustand';
import type {
  OrchestratorPhase,
  OrchestratorPlan,
  OrchestratorToolStep,
  OrchestratorStepResult,
  ThreadMessage,
  PageContext,
  Attachment,
  MissingFieldDef,
  PendingResume,
} from '../lib/types';
import { useClientStore } from './client-store';

// ---------------------------------------------------------------------------
// Store shape
// ---------------------------------------------------------------------------

interface OrchestratorStore {
  // Phase machine
  phase: OrchestratorPhase;

  // Current instruction being processed
  currentInstruction: string;
  currentContext: PageContext;

  // Plan from backend planner
  currentPlan: OrchestratorPlan | null;

  // Execution results
  stepResults: OrchestratorStepResult[];
  synthesizedResponse: string;

  // Regular clarification (from planner)
  clarificationQuestion: string | null;
  clarificationOptions: string[];

  // Missing-field pause/resume
  pendingResume: PendingResume | null;
  missingFieldMode: boolean;
  currentMissingField: MissingFieldDef | null;

  // Conversation history (sent to planner every turn for context)
  conversationHistory: ThreadMessage[];

  // UI state
  inputValue: string;
  pendingFiles: Attachment[];
  isWorkspaceOpen: boolean;
  error: string | null;

  // Actions
  setInput: (value: string) => void;
  addFile: (attachment: Attachment) => void;
  removeFile: (id: string) => void;
  updateFile: (id: string, update: Partial<Attachment>) => void;

  submitInstruction: (
    instruction: string,
    context: PageContext,
    files?: Attachment[],
  ) => Promise<void>;
  confirmPlan: () => Promise<void>;
  cancelPlan: () => void;
  answerClarification: (answer: string) => void;
  openWorkspace: () => void;
  closeWorkspace: () => void;
  reset: () => void;
}

// ---------------------------------------------------------------------------
// Store implementation
// ---------------------------------------------------------------------------

export const useOrchestratorStore = create<OrchestratorStore>((set, get) => ({
  phase: 'idle',
  currentInstruction: '',
  currentContext: { currentPage: '/' },
  currentPlan: null,
  stepResults: [],
  synthesizedResponse: '',
  clarificationQuestion: null,
  clarificationOptions: [],
  pendingResume: null,
  missingFieldMode: false,
  currentMissingField: null,
  conversationHistory: [],
  inputValue: '',
  pendingFiles: [],
  isWorkspaceOpen: false,
  error: null,

  // ---- Input state ----

  setInput: (value) => set({ inputValue: value }),

  addFile: (attachment) =>
    set((s) => ({ pendingFiles: [...s.pendingFiles, attachment] })),

  removeFile: (id) =>
    set((s) => ({ pendingFiles: s.pendingFiles.filter((f) => f.id !== id) })),

  updateFile: (id, update) =>
    set((s) => ({
      pendingFiles: s.pendingFiles.map((f) => (f.id === id ? { ...f, ...update } : f)),
    })),

  // ---- Submit instruction → planning phase ----

  submitInstruction: async (instruction, context, _files) => {
    if (!instruction.trim()) return;

    const { conversationHistory } = get();

    set({
      phase: 'planning',
      currentInstruction: instruction,
      currentContext: context,
      currentPlan: null,
      stepResults: [],
      synthesizedResponse: '',
      clarificationQuestion: null,
      clarificationOptions: [],
      pendingResume: null,
      missingFieldMode: false,
      currentMissingField: null,
      error: null,
      inputValue: '',
      isWorkspaceOpen: true,
    });

    // Add user message to history
    const userMsg: ThreadMessage = {
      role: 'user',
      content: instruction,
      timestamp: Date.now(),
    };

    try {
      // Include attached file storage_refs in context so planner can use extract_factfind_from_document
      const attachedFiles = (_files ?? [])
        .filter((f) => f.storage_ref && !f.uploading && !f.upload_error)
        .map((f) => ({ storage_ref: f.storage_ref, name: f.name }));

      // Call Next.js API route → FastAPI planner
      const res = await fetch('/api/orchestrator', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          instruction,
          context: { ...context, attachedFiles },
          messages: [...conversationHistory, userMsg].slice(-10).map((m) => ({
            role: m.role,
            content: m.content,
          })),
        }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err?.error ?? `Plan request failed (${res.status})`);
      }

      const plan: OrchestratorPlan = await res.json();

      // Update history with user message
      set((s) => ({
        conversationHistory: [...s.conversationHistory, userMsg].slice(-20),
      }));

      switch (plan.type) {
        case 'confirmation_required':
          set({
            phase: 'confirming',
            currentPlan: plan,
            stepResults: plan.steps.map((step, i) => ({
              tool_id: step.tool_id,
              step_index: i,
              label: plan.step_labels[i] ?? step.tool_id,
              status: 'pending',
            })),
          });
          break;

        case 'qna_answer':
          set({
            phase: 'confirming',
            currentPlan: plan,
            stepResults: plan.steps.map((step, i) => ({
              tool_id: step.tool_id,
              step_index: i,
              label: plan.step_labels[i] ?? step.tool_id,
              status: 'pending',
            })),
          });
          // Auto-confirm QnA (no user confirmation needed)
          await get().confirmPlan();
          break;

        case 'clarification_needed':
          set({
            phase: 'clarifying',
            clarificationQuestion: plan.question ?? 'Please clarify your request.',
            clarificationOptions: plan.options ?? [],
            missingFieldMode: false,
          });
          break;

        case 'no_plan':
        default:
          set({
            phase: 'complete',
            synthesizedResponse: plan.message ?? "I couldn't understand that request. Please try rephrasing.",
          });
          _addAssistantMessage(set, get, plan.message ?? "I couldn't understand that request.");
          break;
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Planning failed';
      set({ phase: 'error', error: msg });
    }
  },

  // ---- Confirm plan → executing phase ----

  confirmPlan: async () => {
    const { currentPlan, currentInstruction, currentContext, conversationHistory } = get();
    if (!currentPlan || !currentPlan.steps.length) return;

    set((s) => ({
      phase: 'executing',
      stepResults: s.stepResults.map((r) => ({ ...r, status: 'running' as const })),
    }));

    await _executeConfirm({
      instruction: currentInstruction,
      steps: currentPlan.steps,
      step_labels: currentPlan.step_labels,
      messages: conversationHistory.slice(-6).map((m) => ({ role: m.role, content: m.content })),
      clientId: currentContext.selectedClientId,
    }, set, get);
  },

  // ---- Cancel plan ----

  cancelPlan: () => {
    set({
      phase: 'idle',
      currentPlan: null,
      stepResults: [],
      synthesizedResponse: '',
      pendingResume: null,
      missingFieldMode: false,
      currentMissingField: null,
      isWorkspaceOpen: false,
    });
  },

  // ---- Answer clarification (both regular and missing-field mode) ----

  answerClarification: (answer: string) => {
    const { missingFieldMode, pendingResume, currentInstruction, currentContext } = get();

    if (missingFieldMode && pendingResume) {
      // Missing-field mode: collect the value, advance to next field or resume
      const field = pendingResume.currentMissingField;
      const parsedValue = field.input_type === 'number' ? Number(answer) : answer;

      const updatedOverrides = {
        ...pendingResume.collectedOverrides,
        [field.canonical]: parsedValue,
      };
      // pendingMissingFields holds fields AFTER currentMissingField
      const remainingFields = pendingResume.pendingMissingFields;

      if (remainingFields.length > 0) {
        // More fields to collect — advance to next one
        const nextField = remainingFields[0];
        set((s) => ({
          pendingResume: s.pendingResume
            ? {
                ...s.pendingResume,
                currentMissingField: nextField,
                pendingMissingFields: remainingFields.slice(1),
                collectedOverrides: updatedOverrides,
              }
            : null,
          clarificationQuestion: `Please provide: ${nextField.label}`,
          clarificationOptions: [],
          currentMissingField: nextField,
        }));
      } else {
        // All fields collected — inject overrides and resume
        const resumeState = {
          ...pendingResume,
          collectedOverrides: updatedOverrides,
        };
        _resumeExecution(resumeState, set, get);
      }
    } else {
      // Regular clarification mode — re-plan with the augmented instruction
      const augmented = `${currentInstruction} (clarification: ${answer})`;
      get().submitInstruction(augmented, currentContext);
    }
  },

  // ---- UI controls ----

  openWorkspace: () => set({ isWorkspaceOpen: true }),
  closeWorkspace: () => set({ isWorkspaceOpen: false }),

  reset: () =>
    set({
      phase: 'idle',
      currentPlan: null,
      stepResults: [],
      synthesizedResponse: '',
      clarificationQuestion: null,
      clarificationOptions: [],
      pendingResume: null,
      missingFieldMode: false,
      currentMissingField: null,
      error: null,
      isWorkspaceOpen: false,
    }),
}));

// ---------------------------------------------------------------------------
// Internal: POST to /api/orchestrator/confirm and handle both response types
// ---------------------------------------------------------------------------

async function _executeConfirm(
  body: {
    instruction: string;
    steps: OrchestratorToolStep[];
    step_labels: string[];
    messages: Array<{ role: string; content: string }>;
    clientId?: string | null;
    resume_from_index?: number;
    prior_step_results?: unknown[];
  },
  set: (fn: (s: OrchestratorStore) => Partial<OrchestratorStore>) => void,
  get: () => OrchestratorStore,
) {
  try {
    const res = await fetch('/api/orchestrator/confirm', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err?.error ?? `Execution failed (${res.status})`);
    }

    const data = await res.json();

    // ---- Missing-field pause ----
    if (data.type === 'missing_fields') {
      const missingFields: MissingFieldDef[] = data.missing_fields ?? [];
      const firstField = missingFields[0];

      if (!firstField) {
        throw new Error('Tool paused but no missing field was specified.');
      }

      const resume: PendingResume = {
        steps: data.steps ?? body.steps,
        step_labels: data.step_labels ?? body.step_labels,
        pausedAtIndex: data.paused_at_index ?? 0,
        priorStepResults: data.prior_step_results ?? [],
        instruction: body.instruction,
        messages: body.messages,
        pendingMissingFields: missingFields.slice(1),
        collectedOverrides: {},
        currentMissingField: firstField,
      };

      // Update step results display with prior completed steps
      const priorResults: OrchestratorStepResult[] = (data.prior_step_results ?? []).map(
        (r: { tool_id: string; step_index: number; label: string; status: string; result: unknown; error: string | null; duration_ms: number }) => ({
          tool_id: r.tool_id,
          step_index: r.step_index,
          label: r.label,
          status: r.status === 'completed' ? ('completed' as const) : ('failed' as const),
          result: r.result,
          error: r.error,
          duration_ms: r.duration_ms,
        }),
      );

      set(() => ({
        phase: 'clarifying',
        pendingResume: resume,
        missingFieldMode: true,
        currentMissingField: firstField,
        clarificationQuestion: `Please provide: ${firstField.label}`,
        clarificationOptions: [],
        stepResults: priorResults,
      }));

      return;
    }

    // ---- Execution complete ----
    const executedResults: OrchestratorStepResult[] = (data.step_results ?? []).map(
      (r: {
        tool_id: string;
        step_index: number;
        label: string;
        status: string;
        result: unknown;
        error: string | null;
        duration_ms: number;
      }) => ({
        tool_id: r.tool_id,
        step_index: r.step_index,
        label: r.label,
        status: r.status === 'completed' ? ('completed' as const) : ('failed' as const),
        result: r.result,
        error: r.error,
        duration_ms: r.duration_ms,
      }),
    );

    const summary = data.synthesized_response ?? '';

    set(() => ({
      phase: 'complete',
      stepResults: executedResults,
      synthesizedResponse: summary,
      pendingResume: null,
      missingFieldMode: false,
      currentMissingField: null,
    }));

    _addAssistantMessage(set, get, summary || 'Analysis complete.');

    // Reload workspace so UI reflects any factfind changes made by tools
    const clientId = get().currentContext.selectedClientId;
    if (clientId) {
      useClientStore.getState().loadWorkspace(clientId).catch(() => {});
      _backgroundSyncMemory(clientId);
      if (typeof window !== 'undefined') {
        window.dispatchEvent(
          new CustomEvent('client-analysis-outputs-changed', { detail: { clientId } }),
        );
      }
    }
  } catch (err) {
    const msg = err instanceof Error ? err.message : 'Execution failed';
    set(() => ({ phase: 'error', error: msg }));
  }
}

// ---------------------------------------------------------------------------
// Internal: Resume execution after user provides missing field values
// ---------------------------------------------------------------------------

function _resumeExecution(
  resume: PendingResume,
  set: (fn: (s: OrchestratorStore) => Partial<OrchestratorStore>) => void,
  get: () => OrchestratorStore,
) {
  // Inject overrides into the paused step's parameters
  const updatedSteps = resume.steps.map((step, i) => {
    if (i === resume.pausedAtIndex) {
      return {
        ...step,
        parameters: {
          ...step.parameters,
          _overrides: resume.collectedOverrides,
        },
      };
    }
    return step;
  });

  // Switch to executing phase
  set(() => ({
    phase: 'executing',
    missingFieldMode: false,
    currentMissingField: null,
    clarificationQuestion: null,
    pendingResume: null,
  }));

  _executeConfirm(
    {
      instruction: resume.instruction,
      steps: updatedSteps,
      step_labels: resume.step_labels,
      messages: resume.messages,
      clientId: get().currentContext.selectedClientId,
      resume_from_index: resume.pausedAtIndex,
      prior_step_results: resume.priorStepResults,
    },
    set,
    get,
  );
}

// ---------------------------------------------------------------------------
// Internal helper — add assistant message to history
// ---------------------------------------------------------------------------

function _addAssistantMessage(
  set: (fn: (s: OrchestratorStore) => Partial<OrchestratorStore>) => void,
  _get: () => OrchestratorStore,
  content: string,
) {
  const msg: ThreadMessage = { role: 'assistant', content, timestamp: Date.now() };
  set((s) => ({
    conversationHistory: [...s.conversationHistory, msg].slice(-20),
  }));
}

// ---------------------------------------------------------------------------
// Background AI memory sync — fires after every tool run completes
// ---------------------------------------------------------------------------

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

function _backgroundSyncMemory(clientId: string): void {
  fetch(`${BASE_URL}/api/client-context/${clientId}/enrich-from-factfind`, {
    method: 'POST',
  }).catch(() => {
    // Silently ignore — background sync failures should not affect the user
  });
}
