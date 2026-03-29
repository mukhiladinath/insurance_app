/**
 * orchestrator-handlers.ts — Tool handler registry for the finobi-style orchestrator.
 *
 * All tools execute here on the frontend (Next.js), not on the backend.
 * Each handler calls the existing backend REST APIs and returns a result object.
 *
 * Pattern mirrors finobi-app/lib/tools/handlers/index.ts
 */

import type { ObjectivesAutomationResult } from '../api';
import {
  dispatchObjectivesAutomationStart,
  dispatchObjectivesAutomationDone,
} from '../objectives-automation-events';

const BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

// ---------------------------------------------------------------------------
// Shared fetch helper
// ---------------------------------------------------------------------------

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    ...init,
  });

  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      detail = body?.detail ?? detail;
    } catch { /* ignore */ }
    throw new Error(detail);
  }

  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Tool context (passed to every handler)
// ---------------------------------------------------------------------------

export interface ToolContext {
  clientId?: string | null;
}

// ---------------------------------------------------------------------------
// Tool result wrapper
// ---------------------------------------------------------------------------

export interface ToolResult {
  status: 'success' | 'error';
  data?: unknown;
  error?: string;
  duration_ms?: number;
}

async function runHandler(
  fn: () => Promise<unknown>,
): Promise<ToolResult> {
  const start = Date.now();
  try {
    const data = await fn();
    return { status: 'success', data, duration_ms: Date.now() - start };
  } catch (err) {
    return {
      status: 'error',
      error: err instanceof Error ? err.message : String(err),
      duration_ms: Date.now() - start,
    };
  }
}

function nonEmptyGoalsObjectivesInChanges(changes: Record<string, unknown>): boolean {
  const raw = changes['goals.goals_and_objectives'];
  if (raw === null || raw === undefined) return false;
  const s = typeof raw === 'string' ? raw.trim() : String(raw).trim();
  return s.length > 0;
}

/**
 * Call objectives automation after goals text is saved. Orchestrator tools run in
 * Next.js API routes (no window): the HTTP call must not be gated on window.
 * Browser dispatches are no-ops on the server via objectives-automation-events.
 */
async function runObjectivesAutomationAfterGoalsWritten(clientId: string): Promise<void> {
  dispatchObjectivesAutomationStart(clientId);
  try {
    const autoRes = await fetch(`${BASE}/api/clients/${clientId}/objectives-automation/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ force: false }),
    });
    const body = (await autoRes.json()) as ObjectivesAutomationResult & { detail?: string };
    if (!autoRes.ok) {
      dispatchObjectivesAutomationDone(clientId, {
        skipped: false,
        reason: typeof body.detail === 'string' ? body.detail : `Request failed (${autoRes.status})`,
        tools_run: [],
        outputs_created: 0,
      });
    } else {
      dispatchObjectivesAutomationDone(clientId, {
        skipped: body.skipped,
        reason: body.reason ?? '',
        tools_run: body.tools_run ?? [],
        outputs_created: body.outputs_created ?? 0,
      });
    }
  } catch {
    dispatchObjectivesAutomationDone(clientId, {
      skipped: false,
      reason: 'Could not complete automated analysis (network or server error).',
      tools_run: [],
      outputs_created: 0,
    });
  }
  if (typeof window !== 'undefined') {
    window.dispatchEvent(
      new CustomEvent('client-analysis-outputs-changed', { detail: { clientId } }),
    );
  }
}

// ---------------------------------------------------------------------------
// Client & Factfind handlers
// ---------------------------------------------------------------------------

async function get_client_factfind(
  params: { clientId: string; section?: string },
  _ctx: ToolContext,
): Promise<ToolResult> {
  return runHandler(async () => {
    const data = await apiFetch<Record<string, unknown>>(
      `/api/clients/${params.clientId}/factfind`
    );
    if (params.section && typeof data.sections === 'object' && data.sections !== null) {
      const sections = data.sections as Record<string, unknown>;
      return { section: params.section, data: sections[params.section] ?? {} };
    }
    return data;
  });
}

async function update_client_factfind(
  params: Record<string, unknown>,
  _ctx: ToolContext,
): Promise<ToolResult> {
  return runHandler(async () => {
    const clientId = params.clientId as string;
    const changes = (params.changes ?? {}) as Record<string, unknown>;
    // Skip the API call if there are no actual changes to write
    if (!changes || Object.keys(changes).length === 0) {
      return { skipped: true, reason: 'No changes provided — factfind not modified.' };
    }
    const result = await apiFetch<unknown>(`/api/clients/${clientId}/factfind`, {
      method: 'PATCH',
      body: JSON.stringify({ changes }),
    });
    if (nonEmptyGoalsObjectivesInChanges(changes)) {
      await runObjectivesAutomationAfterGoalsWritten(clientId);
    }
    return result;
  });
}

async function get_client_profile(
  params: { clientId: string },
  _ctx: ToolContext,
): Promise<ToolResult> {
  return runHandler(async () => {
    return apiFetch<unknown>(`/api/clients/${params.clientId}`);
  });
}

async function list_clients(
  _params: Record<string, unknown>,
  _ctx: ToolContext,
): Promise<ToolResult> {
  const userId = process.env.NEXT_PUBLIC_USER_ID ?? 'advisor-1';
  return runHandler(async () => {
    return apiFetch<unknown>(`/api/clients?user_id=${encodeURIComponent(userId)}`);
  });
}

// ---------------------------------------------------------------------------
// AI Memory handlers
// ---------------------------------------------------------------------------

async function read_client_memory(
  params: { clientId: string; category: string },
  _ctx: ToolContext,
): Promise<ToolResult> {
  return runHandler(async () => {
    return apiFetch<unknown>(
      `/api/client-context/${params.clientId}/memories/${params.category}`
    );
  });
}

async function search_client_memory(
  params: { clientId: string; query: string },
  _ctx: ToolContext,
): Promise<ToolResult> {
  return runHandler(async () => {
    return apiFetch<unknown>(
      `/api/client-context/${params.clientId}/search?query=${encodeURIComponent(params.query)}`
    );
  });
}

// ---------------------------------------------------------------------------
// Insurance analysis tool handlers (delegate to backend /api/tools/{name}/run)
// ---------------------------------------------------------------------------

/** Special signal returned when critical fields are missing — pauses the run */
export interface MissingFieldsSignal {
  _missing_fields: true;
  missing_fields: Array<{
    path: string;
    canonical: string;
    label: string;
    input_type: string;
  }>;
  backend_tool_name: string;
  params: { clientId: string };
  partial_input: Record<string, unknown>;
}

async function runInsuranceTool(
  backendToolName: string,
  params: Record<string, unknown>,
  _ctx: ToolContext,
): Promise<ToolResult> {
  const clientId = params.clientId as string;
  const overrides = (params._overrides ?? {}) as Record<string, unknown>;
  const start = Date.now();
  try {
    // 1. Build nested tool input via backend (factfind → canonical facts → tool schema)
    const buildRes = await apiFetch<{
      tool_input: Record<string, unknown>;
      missing_fields: Array<{ path: string; canonical: string; label: string; input_type: string }>;
    }>(`/api/client-context/${clientId}/build-tool-input`, {
      method: 'POST',
      body: JSON.stringify({
        tool_name: backendToolName,
        overrides,
      }),
    });

    // 2. If critical fields are still missing, signal a pause
    if (buildRes.missing_fields.length > 0) {
      const signal: MissingFieldsSignal = {
        _missing_fields: true,
        missing_fields: buildRes.missing_fields,
        backend_tool_name: backendToolName,
        params: { clientId },
        partial_input: buildRes.tool_input,
      };
      return { status: 'success', data: signal, duration_ms: Date.now() - start };
    }

    // 3. Run the tool with the fully-built nested input
    const result = await apiFetch<unknown>(`/api/tools/${backendToolName}/run`, {
      method: 'POST',
      body: JSON.stringify(buildRes.tool_input),
    });

    return { status: 'success', data: result, duration_ms: Date.now() - start };
  } catch (err) {
    return {
      status: 'error',
      error: err instanceof Error ? err.message : String(err),
      duration_ms: Date.now() - start,
    };
  }
}

// Actual backend tool registry names (from /api/tools)
// _overrides in params carries user-supplied values for missing critical fields
async function life_insurance_in_super(
  params: Record<string, unknown>,
  ctx: ToolContext,
): Promise<ToolResult> {
  return runInsuranceTool('purchase_retain_life_insurance_in_super', params, ctx);
}

async function life_tpd_policy(
  params: Record<string, unknown>,
  ctx: ToolContext,
): Promise<ToolResult> {
  return runInsuranceTool('purchase_retain_life_tpd_policy', params, ctx);
}

async function income_protection_policy(
  params: Record<string, unknown>,
  ctx: ToolContext,
): Promise<ToolResult> {
  return runInsuranceTool('purchase_retain_income_protection_policy', params, ctx);
}

async function ip_in_super(
  params: Record<string, unknown>,
  ctx: ToolContext,
): Promise<ToolResult> {
  return runInsuranceTool('purchase_retain_ip_in_super', params, ctx);
}

async function trauma_critical_illness(
  params: Record<string, unknown>,
  ctx: ToolContext,
): Promise<ToolResult> {
  return runInsuranceTool('purchase_retain_trauma_ci_policy', params, ctx);
}

async function tpd_policy_assessment(
  params: Record<string, unknown>,
  ctx: ToolContext,
): Promise<ToolResult> {
  return runInsuranceTool('tpd_policy_assessment', params, ctx);
}

async function tpd_in_super(
  params: Record<string, unknown>,
  ctx: ToolContext,
): Promise<ToolResult> {
  return runInsuranceTool('purchase_retain_tpd_in_super', params, ctx);
}

// ---------------------------------------------------------------------------
// Extract factfind fields from an uploaded document and auto-save them
// ---------------------------------------------------------------------------

async function extract_factfind_from_document(
  params: Record<string, unknown>,
  _ctx: ToolContext,
): Promise<ToolResult> {
  return runHandler(async () => {
    const clientId = params.clientId as string;
    const storage_ref = params.storage_ref as string;
    if (!storage_ref) throw new Error('storage_ref is required to extract factfind from document');
    const res = await apiFetch<{
      fields?: Array<{ field_path: string }>;
    }>(`/api/clients/${clientId}/factfind/extract-from-upload`, {
      method: 'POST',
      body: JSON.stringify({ storage_ref }),
    });
    const filledObjectives = res.fields?.some((f) => f.field_path === 'goals.goals_and_objectives');
    if (filledObjectives) {
      await runObjectivesAutomationAfterGoalsWritten(clientId);
    }
    return res;
  });
}

// ---------------------------------------------------------------------------
// SOA handler
// ---------------------------------------------------------------------------

async function generate_soa(
  params: { clientId: string },
  _ctx: ToolContext,
): Promise<ToolResult> {
  return runHandler(async () => {
    // SOA needs a conversation_id; use workspace to find it
    const workspace = await apiFetch<Record<string, unknown>>(
      `/api/workspace/${params.clientId}`
    );
    const conversationId = workspace.active_conversation_id as string | null;
    if (!conversationId) {
      throw new Error('No active conversation found for SOA generation. Please start a chat first.');
    }
    return apiFetch<unknown>('/api/soa/generate', {
      method: 'POST',
      body: JSON.stringify({ conversation_id: conversationId }),
    });
  });
}

// ---------------------------------------------------------------------------
// Tool handler registry
// ---------------------------------------------------------------------------

type HandlerFn = (params: Record<string, unknown>, ctx: ToolContext) => Promise<ToolResult>;

export const TOOL_HANDLERS: Record<string, HandlerFn> = {
  get_client_factfind:       get_client_factfind as HandlerFn,
  update_client_factfind:    update_client_factfind as HandlerFn,
  get_client_profile:        get_client_profile as HandlerFn,
  list_clients:              list_clients as HandlerFn,
  read_client_memory:        read_client_memory as HandlerFn,
  search_client_memory:      search_client_memory as HandlerFn,
  life_insurance_in_super:   life_insurance_in_super as HandlerFn,
  life_tpd_policy:           life_tpd_policy as HandlerFn,
  income_protection_policy:  income_protection_policy as HandlerFn,
  ip_in_super:               ip_in_super as HandlerFn,
  trauma_critical_illness:   trauma_critical_illness as HandlerFn,
  tpd_policy_assessment:     tpd_policy_assessment as HandlerFn,
  tpd_in_super:              tpd_in_super as HandlerFn,
  generate_soa:              generate_soa as HandlerFn,
  extract_factfind_from_document: extract_factfind_from_document as HandlerFn,
};

// ---------------------------------------------------------------------------
// Parameter resolver — handles {{stepN.fieldName}} references
// ---------------------------------------------------------------------------

export function resolveParameters(
  parameters: Record<string, unknown>,
  stepResults: Array<{ result?: unknown }>,
): Record<string, unknown> {
  const resolved: Record<string, unknown> = {};

  for (const [key, value] of Object.entries(parameters)) {
    if (typeof value === 'string' && value.startsWith('{{') && value.endsWith('}}')) {
      // e.g. "{{step0.clientId}}" → stepResults[0].result.clientId
      const inner = value.slice(2, -2).trim(); // "step0.clientId"
      const dotIndex = inner.indexOf('.');
      if (dotIndex > 0) {
        const stepPart = inner.slice(0, dotIndex); // "step0"
        const fieldPart = inner.slice(dotIndex + 1); // "clientId"
        const stepIndex = parseInt(stepPart.replace('step', ''), 10);
        if (!isNaN(stepIndex) && stepResults[stepIndex]) {
          const stepResult = stepResults[stepIndex].result;
          if (stepResult && typeof stepResult === 'object') {
            resolved[key] = (stepResult as Record<string, unknown>)[fieldPart] ?? value;
          } else {
            resolved[key] = value;
          }
        } else {
          resolved[key] = value;
        }
      } else {
        resolved[key] = value;
      }
    } else {
      resolved[key] = value;
    }
  }

  return resolved;
}

// ---------------------------------------------------------------------------
// Sequential step executor
// ---------------------------------------------------------------------------

export async function executeToolSteps(
  steps: Array<{ tool_id: string; parameters: Record<string, unknown> }>,
  ctx: ToolContext,
): Promise<ToolResult[]> {
  const results: ToolResult[] = [];

  for (const step of steps) {
    const handler = TOOL_HANDLERS[step.tool_id];
    if (!handler) {
      results.push({
        status: 'error',
        error: `Unknown tool: ${step.tool_id}`,
      });
      continue;
    }

    // Resolve parameter references from prior step results
    const resolvedParams = resolveParameters(step.parameters, results);

    const result = await handler(resolvedParams, ctx);
    results.push(result);
  }

  return results;
}
