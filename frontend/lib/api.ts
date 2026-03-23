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
  }>;
  tool_hint?: string;
}

export function sendMessage(payload: SendMessagePayload): Promise<ApiChatResponse> {
  return request<ApiChatResponse>('/api/chat/message', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}
