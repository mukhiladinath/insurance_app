/**
 * api.ts — Typed HTTP client for the Insurance Advisory backend.
 *
 * All functions throw on non-2xx responses.
 * Base URL and user ID are read from NEXT_PUBLIC_* env vars.
 */

import type {
  ApiConversation,
  ApiMessage,
  ApiChatResponse,
  ApiTool,
  ApiHealthResponse,
  SOAGenerateResponse,
  ConversationDocument,
} from './types';

const BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
export const USER_ID = process.env.NEXT_PUBLIC_USER_ID ?? 'advisor-1';

// ---------------------------------------------------------------------------
// Shared fetch wrapper
// ---------------------------------------------------------------------------

async function request<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    ...init,
  });

  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      detail = body?.detail ?? detail;
    } catch {
      // ignore parse errors
    }
    throw new Error(detail);
  }

  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Health
// ---------------------------------------------------------------------------

export function health(): Promise<ApiHealthResponse> {
  return request<ApiHealthResponse>('/api/health');
}

// ---------------------------------------------------------------------------
// Tools
// ---------------------------------------------------------------------------

export function listTools(): Promise<ApiTool[]> {
  return request<ApiTool[]>('/api/tools');
}

// ---------------------------------------------------------------------------
// Conversations
// ---------------------------------------------------------------------------

export async function deleteConversation(conversationId: string): Promise<void> {
  const res = await fetch(`${BASE}/api/conversations/${conversationId}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
}

export function listConversations(
  userId: string = USER_ID,
  limit = 50,
  skip = 0,
): Promise<ApiConversation[]> {
  const params = new URLSearchParams({
    user_id: userId,
    limit: String(limit),
    skip: String(skip),
  });
  return request<ApiConversation[]>(`/api/conversations?${params}`);
}

export function getMessages(
  conversationId: string,
  limit = 100,
  skip = 0,
): Promise<ApiMessage[]> {
  const params = new URLSearchParams({
    limit: String(limit),
    skip: String(skip),
  });
  return request<ApiMessage[]>(
    `/api/conversations/${conversationId}/messages?${params}`,
  );
}

// ---------------------------------------------------------------------------
// Chat
// ---------------------------------------------------------------------------

export interface SendMessagePayload {
  user_id: string;
  conversation_id?: string | null;
  message: string;
  attached_files?: Array<{
    filename: string;
    content_type: string;
    size_bytes?: number;
    storage_ref?: string;
  }>;
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

/**
 * Upload a file to the backend for text and client-fact extraction.
 * Returns a storage_ref that must be included in attached_files when sending a message.
 */
export async function uploadFile(
  file: File,
  userId: string,
  conversationId?: string | null,
): Promise<DocumentUploadResponse> {
  const form = new FormData();
  form.append('file', file);
  form.append('user_id', userId);
  if (conversationId) {
    form.append('conversation_id', conversationId);
  }

  const res = await fetch(`${BASE}/api/upload`, {
    method: 'POST',
    body: form,
    // Do NOT set Content-Type header — browser sets it with the correct boundary for multipart
  });

  if (!res.ok) {
    let detail = `Upload failed (HTTP ${res.status})`;
    try {
      const body = await res.json();
      detail = body?.detail ?? detail;
    } catch {
      // ignore
    }
    throw new Error(detail);
  }

  return res.json() as Promise<DocumentUploadResponse>;
}

// ---------------------------------------------------------------------------
// SOA generation
// ---------------------------------------------------------------------------

/**
 * Generate (or update) SOA sections for a conversation.
 * Pass `answers` to fill previously identified missing fields.
 */
export function generateSOA(
  conversationId: string,
  answers?: Record<string, string>,
): Promise<SOAGenerateResponse> {
  return request<SOAGenerateResponse>('/api/soa/generate', {
    method: 'POST',
    body: JSON.stringify({ conversation_id: conversationId, answers }),
  });
}

/**
 * Fetch the saved SOA draft for a conversation.
 * Throws (404) if no draft has been saved yet.
 */
export function getSOADraft(conversationId: string): Promise<SOAGenerateResponse> {
  return request<SOAGenerateResponse>(`/api/soa/${conversationId}`);
}

// ---------------------------------------------------------------------------
// Documents
// ---------------------------------------------------------------------------

export function listDocuments(conversationId: string): Promise<ConversationDocument[]> {
  return request<ConversationDocument[]>(`/api/conversations/${conversationId}/documents`);
}

/** Returns a URL that streams the file directly from the backend. */
export function getDocumentUrl(storageRef: string): string {
  return `${BASE}/api/upload/${storageRef}`;
}
