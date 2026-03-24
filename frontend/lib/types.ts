// ---------------------------------------------------------------------------
// API response types — mirror backend Pydantic schemas exactly
// ---------------------------------------------------------------------------

export interface ApiHealthResponse {
  status: string;
  service: string;
}

export interface ApiConversation {
  id: string;
  title: string;
  status: string;
  updated_at: string;       // ISO datetime string
  last_message_at: string | null;
}

export interface ApiMessage {
  id: string;
  conversation_id: string;
  agent_run_id: string | null;
  role: 'user' | 'assistant';
  content: string;
  structured_payload: Record<string, unknown> | null;
  created_at: string;       // ISO datetime string
}

export interface ApiTool {
  name: string;
  version: string;
  description: string;
  input_schema: Record<string, unknown>;
}

export interface ApiChatResponse {
  conversation: {
    id: string;
    title: string;
    user_id: string;
    status: string;
    created_at: string;
    updated_at: string;
  };
  user_message: {
    id: string;
    role: string;
    content: string;
    created_at: string;
  };
  assistant_message: {
    id: string;
    role: string;
    content: string;
    structured_payload: Record<string, unknown> | null;
    created_at: string;
  };
  agent_run: {
    id: string;
    intent: string | null;
    selected_tool: string | null;
    status: string;
  };
  tool_result: {
    tool_name: string;
    tool_version: string;
    status: string;
    payload: Record<string, unknown>;
    warnings: string[];
  } | null;
}

// ---------------------------------------------------------------------------
// Frontend UI types
// ---------------------------------------------------------------------------

export type MessageRole = 'user' | 'assistant' | 'system';

export interface Attachment {
  id: string;
  name: string;
  type: string;
  size: number;
  url?: string;
  storage_ref?: string;       // returned by /api/upload — identifies the document in the backend
  uploading?: boolean;        // true while the file is being uploaded to the backend
  upload_error?: string;      // set if upload failed
  facts_summary?: string;     // short summary of client facts detected in the document
}

export interface Message {
  id: string;
  role: MessageRole;
  content: string;
  timestamp: Date;
  attachments?: Attachment[];
  isStreaming?: boolean;
}

export interface Chat {
  id: string;
  title: string;
  lastMessage: string;
  timestamp: Date;
  messageCount: number;
}

export interface QuickPrompt {
  id: string;
  title: string;
  description: string;
  iconName: string;
  category: string;
}

// ---------------------------------------------------------------------------
// SOA (Statement of Advice) types
// ---------------------------------------------------------------------------

export interface SOASection {
  template_number: number;
  template_name: string;
  title: string;
  our_recommendation: string;
  why_appropriate: string;
  what_to_consider: string;
  more_information: string;
}

export interface SOAMissingQuestion {
  id: string;
  question: string;
}

export interface SOADraftPayload {
  type: 'soa_draft';
  sections: SOASection[];
  missing_questions: SOAMissingQuestion[];
}

export interface SOAGenerateResponse {
  sections: SOASection[];
  missing_questions: SOAMissingQuestion[];
}

export interface ConversationDocument {
  id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  facts_found: boolean;
  facts_summary: string;
  created_at: string;
}

export type BackendStatus = 'online' | 'offline' | 'connecting';

export interface WorkspaceStatus {
  backend: BackendStatus;
  model: string;
  toolsAvailable: number;
  lastSync?: Date;
}
