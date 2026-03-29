/**
 * api.ts — Typed HTTP client for the Insurance Advisory backend.
 */

import type {
  ApiConversation,
  ApiMessage,
  ApiChatResponse,
  ApiTool,
  ApiHealthResponse,
  SOAGenerateResponse,
  ConversationDocument,
  AgentRunResponse,
  ClientWorkspace,
  ClientFacts,
  AdvisoryNote,
  MissingField,
  WorkspaceRunResponse,
} from './types';

const BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
export const USER_ID = process.env.NEXT_PUBLIC_USER_ID ?? 'advisor-1';

// ---------------------------------------------------------------------------
// Shared fetch wrapper
// ---------------------------------------------------------------------------

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    cache: 'no-store',
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
// Health & tools
// ---------------------------------------------------------------------------

export function health(): Promise<ApiHealthResponse> {
  return request<ApiHealthResponse>('/api/health');
}

export function listTools(): Promise<ApiTool[]> {
  return request<ApiTool[]>('/api/tools');
}

// ---------------------------------------------------------------------------
// New client-workspace API
// ---------------------------------------------------------------------------

export interface ApiClient {
  id: string;
  user_id: string;
  name: string;
  email: string | null;
  phone: string | null;
  date_of_birth: string | null;
  status: string;
  created_at: string;
  updated_at: string;
}

export function createClient(name: string, userId: string = USER_ID): Promise<ApiClient> {
  return request<ApiClient>('/api/clients', {
    method: 'POST',
    body: JSON.stringify({ user_id: userId, name }),
  });
}

export async function listClients(userId: string = USER_ID): Promise<ApiClient[]> {
  const data = await request<{ clients: ApiClient[] }>(
    `/api/clients?user_id=${encodeURIComponent(userId)}`
  );
  return data.clients;
}

export async function archiveClient(clientId: string): Promise<void> {
  await request<unknown>(`/api/clients/${clientId}`, { method: 'DELETE' });
}

/** Transform WorkspaceOut (from /api/workspace/{id}) into the ClientWorkspace shape the UI expects. */
function transformWorkspaceOut(data: Record<string, unknown>): ClientWorkspace {
  const factfind = (data.factfind ?? {}) as Record<string, unknown>;
  const sections = (factfind.sections ?? {}) as Record<string, Record<string, Record<string, unknown>>>;

  const clientFacts: ClientFacts = { personal: {}, financial: {}, insurance: {}, health: {}, goals: {} };
  for (const [section, fields] of Object.entries(sections)) {
    if (section in clientFacts) {
      const flat: Record<string, unknown> = {};
      for (const [fieldName, fieldData] of Object.entries(fields)) {
        if (fieldData && typeof fieldData === 'object' && 'value' in fieldData) {
          const v = fieldData.value;
          if (v !== null && v !== undefined && v !== '') flat[fieldName] = v;
        }
      }
      (clientFacts as Record<string, unknown>)[section] = flat;
    }
  }

  const client = (data.client ?? {}) as Record<string, unknown>;
  const pending = (data.pending_clarification ?? null) as Record<string, unknown> | null;

  return {
    client_id: (client.id as string) ?? '',
    workspace_id: (data.workspace_id as string) ?? '',
    client_facts: clientFacts,
    advisory_notes: (data.advisory_notes ?? {}) as Record<string, AdvisoryNote>,
    scratch_pad: (data.scratch_pad ?? []) as Array<{ category: string; content: string; created_at: string }>,
    summary: '',
    turn_count: 0,
    active_conversation_id: (data.active_conversation_id as string | null) ?? null,
    pending_clarification: pending
      ? {
          resume_token: pending.resume_token as string,
          question: pending.question as string,
          missing_fields: (pending.missing_fields ?? []) as MissingField[],
        }
      : null,
  };
}

export async function getWorkspace(clientId: string): Promise<ClientWorkspace> {
  const data = await request<Record<string, unknown>>(`/api/workspace/${clientId}`);
  return transformWorkspaceOut(data);
}

export interface WorkspaceRunPayload {
  user_id: string;
  message: string;
  conversation_id?: string | null;
  attached_files?: Array<{
    filename: string;
    content_type: string;
    size_bytes: number;
    storage_ref: string;
  }>;
  resume_token?: string | null;
  clarification_answer?: string | null;
  rerun_from_saved_run_id?: string | null;
  patched_inputs?: Record<string, unknown> | null;
  save_run_as?: string | null;
}

export function runWorkspace(
  clientId: string,
  payload: WorkspaceRunPayload,
): Promise<WorkspaceRunResponse> {
  return request<WorkspaceRunResponse>(`/api/workspace/${clientId}/run`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function patchFactfindDirect(
  clientId: string,
  changes: Record<string, unknown>,
): Promise<unknown> {
  return request<unknown>(`/api/clients/${clientId}/factfind`, {
    method: 'PATCH',
    body: JSON.stringify({ changes }),
  });
}

/** Accept all or specific fields from a proposal. Pass null fieldPaths to accept all. */
export function acceptProposal(
  clientId: string,
  proposalId: string,
  fieldPaths: string[] | null = null,
): Promise<unknown> {
  return request<unknown>(`/api/clients/${clientId}/factfind/proposals/${proposalId}/accept`, {
    method: 'POST',
    body: JSON.stringify({ field_paths: fieldPaths }),
  });
}

export function rejectProposal(clientId: string, proposalId: string): Promise<unknown> {
  return request<unknown>(`/api/clients/${clientId}/factfind/proposals/${proposalId}/reject`, {
    method: 'POST',
  });
}

// ---------------------------------------------------------------------------
// Legacy conversations API (kept for SOA and document listing)
// ---------------------------------------------------------------------------

export function listConversations(userId: string = USER_ID, limit = 50, skip = 0): Promise<ApiConversation[]> {
  const params = new URLSearchParams({ user_id: userId, limit: String(limit), skip: String(skip) });
  return request<ApiConversation[]>(`/api/conversations?${params}`);
}

export function getMessages(conversationId: string, limit = 100, skip = 0): Promise<ApiMessage[]> {
  const params = new URLSearchParams({ limit: String(limit), skip: String(skip) });
  return request<ApiMessage[]>(`/api/conversations/${conversationId}/messages?${params}`);
}

export async function deleteConversation(conversationId: string): Promise<void> {
  const res = await fetch(`${BASE}/api/conversations/${conversationId}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
}

// ---------------------------------------------------------------------------
// Legacy agent run (kept for reference, no longer used by AIBar)
// ---------------------------------------------------------------------------

export interface AgentRunPayload {
  user_id: string;
  message: string;
  conversation_id?: string | null;
  conversation_title?: string;
  attached_files?: Array<{
    filename: string;
    content_type: string;
    size_bytes: number;
    storage_ref: string;
  }>;
}

export function runAgent(payload: AgentRunPayload): Promise<AgentRunResponse> {
  return request<AgentRunResponse>('/api/agent/run', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/** @deprecated Use getWorkspace(clientId) instead */
export function getClientWorkspace(conversationId: string): Promise<ClientWorkspace> {
  return request<ClientWorkspace>(`/api/agent/workspace/${conversationId}`);
}

/** @deprecated Use patchFactfindDirect(clientId, changes) instead */
export function patchClientFacts(
  conversationId: string,
  facts: Record<string, Record<string, unknown>>,
): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>(`/api/agent/workspace/${conversationId}/facts`, {
    method: 'PATCH',
    body: JSON.stringify({ facts }),
  });
}

// ---------------------------------------------------------------------------
// Legacy chat
// ---------------------------------------------------------------------------

export interface SendMessagePayload {
  user_id: string;
  conversation_id?: string | null;
  message: string;
  attached_files?: Array<{ filename: string; content_type: string; size_bytes?: number; storage_ref?: string }>;
  tool_hint?: string;
}

export function sendMessage(payload: SendMessagePayload): Promise<ApiChatResponse> {
  return request<ApiChatResponse>('/api/chat/message', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

// ---------------------------------------------------------------------------
// Document upload
// ---------------------------------------------------------------------------

export interface DocumentUploadResponse {
  storage_ref: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  extracted_text_preview: string;
  facts_found: boolean;
  facts_summary: string;
}

export async function uploadFile(
  file: File,
  userId: string,
  conversationId?: string | null,
  clientId?: string | null,
): Promise<DocumentUploadResponse> {
  const form = new FormData();
  form.append('file', file);
  form.append('user_id', userId);
  if (conversationId) form.append('conversation_id', conversationId);
  if (clientId) form.append('client_id', clientId);

  const res = await fetch(`${BASE}/api/upload`, { method: 'POST', body: form });

  if (!res.ok) {
    let detail = `Upload failed (HTTP ${res.status})`;
    try { const body = await res.json(); detail = body?.detail ?? detail; } catch { /* ignore */ }
    throw new Error(detail);
  }

  return res.json() as Promise<DocumentUploadResponse>;
}

// ---------------------------------------------------------------------------
// SOA
// ---------------------------------------------------------------------------

export function generateSOA(conversationId: string, answers?: Record<string, string>): Promise<SOAGenerateResponse> {
  return request<SOAGenerateResponse>('/api/soa/generate', {
    method: 'POST',
    body: JSON.stringify({ conversation_id: conversationId, answers }),
  });
}

export function getSOADraft(conversationId: string): Promise<SOAGenerateResponse> {
  return request<SOAGenerateResponse>(`/api/soa/${conversationId}`);
}

// ---------------------------------------------------------------------------
// Documents
// ---------------------------------------------------------------------------

export function listDocuments(conversationId: string): Promise<ConversationDocument[]> {
  return request<ConversationDocument[]>(`/api/conversations/${conversationId}/documents`);
}

/** Documents for a client profile (by client_id and/or workspace active conversation). */
export function listWorkspaceDocuments(clientId: string): Promise<ConversationDocument[]> {
  return request<ConversationDocument[]>(`/api/workspace/${clientId}/documents`);
}

export interface ObjectivesAutomationResult {
  skipped: boolean;
  reason: string;
  tools_run: string[];
  outputs_created: number;
}

/** Run insurance tools inferred from fact-find Goals & objectives (deduped by text fingerprint). */
export function runObjectivesAutomation(
  clientId: string,
  options?: { force?: boolean },
): Promise<ObjectivesAutomationResult> {
  return request<ObjectivesAutomationResult>(`/api/clients/${clientId}/objectives-automation/run`, {
    method: 'POST',
    body: JSON.stringify({ force: options?.force ?? false }),
  });
}

export function getDocumentUrl(storageRef: string): string {
  return `${BASE}/api/upload/${storageRef}`;
}

// ---------------------------------------------------------------------------
// Client AI Memory (client-context routes)
// ---------------------------------------------------------------------------

export interface ClientMemoryDoc {
  client_id: string;
  category: string;
  category_label: string;
  content: string;
  last_updated?: string;
  fact_count: number;
  sources: Array<{ filename: string; date: string; fact_count: number }>;
}

export function getClientMemories(clientId: string): Promise<{ client_id: string; memories: ClientMemoryDoc[] }> {
  return request<{ client_id: string; memories: ClientMemoryDoc[] }>(
    `/api/client-context/${clientId}/memories`
  );
}

export function getClientMemoryCategory(clientId: string, category: string): Promise<ClientMemoryDoc> {
  return request<ClientMemoryDoc>(`/api/client-context/${clientId}/memories/${category}`);
}

export async function uploadEnrichClientMemory(
  clientId: string,
  file: File,
): Promise<{ updated_categories: string[]; facts_extracted: number; filename?: string }> {
  const form = new FormData();
  form.append('file', file);

  const res = await fetch(`${BASE}/api/client-context/${clientId}/upload-enrich`, {
    method: 'POST',
    body: form,
  });

  if (!res.ok) {
    let detail = `Upload failed (HTTP ${res.status})`;
    try { const body = await res.json(); detail = body?.detail ?? detail; } catch { /* ignore */ }
    throw new Error(detail);
  }

  return res.json();
}

export function syncClientMemoryFromFactfind(
  clientId: string,
): Promise<{ updated_categories: string[]; source: string }> {
  return request<{ updated_categories: string[]; source: string }>(
    `/api/client-context/${clientId}/enrich-from-factfind`,
    { method: 'POST' }
  );
}

export function searchClientMemory(
  clientId: string,
  query: string,
): Promise<{ client_id: string; query: string; results: ClientMemoryDoc[] }> {
  return request<{ client_id: string; query: string; results: ClientMemoryDoc[] }>(
    `/api/client-context/${clientId}/search?query=${encodeURIComponent(query)}`
  );
}
