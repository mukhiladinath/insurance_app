// ---------------------------------------------------------------------------
// API response types — mirror backend Pydantic schemas
// ---------------------------------------------------------------------------

export interface ApiHealthResponse {
  status: string;
  service: string;
}

export interface ApiConversation {
  id: string;
  title: string;
  status: string;
  updated_at: string;
  last_message_at: string | null;
}

export interface ApiMessage {
  id: string;
  conversation_id: string;
  agent_run_id: string | null;
  role: 'user' | 'assistant';
  content: string;
  structured_payload: Record<string, unknown> | null;
  created_at: string;
}

export interface ApiTool {
  name: string;
  version: string;
  description: string;
  input_schema: Record<string, unknown>;
}

// Legacy chat response (kept for backwards compat)
export interface ApiChatResponse {
  conversation: { id: string; title: string; user_id: string; status: string; created_at: string; updated_at: string };
  user_message: { id: string; role: string; content: string; created_at: string };
  assistant_message: { id: string; role: string; content: string; structured_payload: Record<string, unknown> | null; created_at: string };
  agent_run: { id: string; intent: string | null; selected_tool: string | null; status: string };
  tool_result: { tool_name: string; tool_version: string; status: string; payload: Record<string, unknown>; warnings: string[] } | null;
}

// ---------------------------------------------------------------------------
// Shared sub-types
// ---------------------------------------------------------------------------

export interface PlanStep {
  step_id: string;
  tool_name: string;
  description: string;
  depends_on: string[];
  rationale: string;
}

export interface StepResult {
  step_id: string;
  tool_name: string;
  description: string;
  status: 'completed' | 'failed' | 'skipped' | 'cached';
  error: string | null;
  cache_source_run_id?: string | null;
}

export interface DataCard {
  step_id: string;
  tool_name: string;
  type: string;
  title: string;
  display_hint: 'recommendation_card' | 'summary_with_actions' | 'gap_analysis_card' | 'table';
  data: Record<string, unknown>;
}

export interface MissingField {
  field_path: string;   // e.g. "personal.age"
  label: string;        // e.g. "Client Age"
  section: string;      // e.g. "personal"
  required: boolean;
}

export interface ProposedFieldOut {
  field_path: string;
  label: string;
  current_value: unknown;
  proposed_value: unknown;
  confidence: number;
  evidence: string;
}

export interface ProposedPatchOut {
  proposal_id: string;
  source_document_id: string;
  fields: ProposedFieldOut[];
}

// ---------------------------------------------------------------------------
// New workspace run response (POST /api/workspace/{clientId}/run)
// ---------------------------------------------------------------------------

export interface WorkspaceRunResponse {
  run_id: string;
  client_id: string;
  workspace_id: string;
  conversation_id: string;
  user_message_id: string;
  assistant_message_id: string | null;
  run_status: 'completed' | 'awaiting_clarification' | 'failed' | 'partial';
  assistant_content: string;
  clarification_needed: boolean;
  clarification_question: string | null;
  missing_fields: MissingField[];
  resume_token: string | null;
  plan_steps: PlanStep[];
  step_results: StepResult[];
  data_cards: DataCard[];
  saved_run_id: string | null;
  ui_actions: Array<{ type: string; payload: Record<string, unknown> }>;
  context_snapshot_id: string | null;
  context_summary: Record<string, unknown>;
  errors: string[];
  proposed_factfind_patches: ProposedPatchOut | null;
}

// ---------------------------------------------------------------------------
// Legacy agent run response (kept for old /api/agent/run compat)
// ---------------------------------------------------------------------------

export interface ContextLoaded {
  memory_sections: string[];
  history_depth: number;
  advisory_notes_loaded: boolean;
  facts_loaded: Record<string, string[]>;
}

export interface AgentRunResponse {
  conversation: { id: string; title: string; user_id: string; status: string; created_at: string; updated_at: string };
  user_message_id: string;
  assistant_message_id: string | null;
  assistant_content: string;
  agent_run: { id: string; intent: string | null; status: string };
  plan_steps: PlanStep[];
  step_results: StepResult[];
  data_cards: DataCard[];
  clarification_needed: boolean;
  clarification_question: string | null;
  missing_context: string[];
  context_loaded: ContextLoaded;
}

// ---------------------------------------------------------------------------
// Client Workspace (profile data — GET /api/workspace/{clientId})
// ---------------------------------------------------------------------------

export interface AdvisoryNote {
  verdict: string;
  recommendation: string;
  key_numbers: Record<string, unknown>;
  key_findings: string;
  analysed_at: string;
  agent_run_id: string;
}

export interface ClientFacts {
  personal: Record<string, unknown>;
  financial: Record<string, unknown>;
  insurance: Record<string, unknown>;
  health: Record<string, unknown>;
  goals: Record<string, unknown>;
}

/** Stable fallback when workspace is not loaded — must be a shared reference or FactFind re-sync wipes edits every render. */
export const EMPTY_CLIENT_FACTS: ClientFacts = {
  personal: {},
  financial: {},
  insurance: {},
  health: {},
  goals: {},
};

export interface ClientWorkspace {
  client_id: string;
  workspace_id: string;
  client_facts: ClientFacts;
  advisory_notes: Record<string, AdvisoryNote>;
  scratch_pad: Array<{ category: string; content: string; created_at: string }>;
  summary: string;
  turn_count: number;
  active_conversation_id: string | null;
  pending_clarification: {
    resume_token: string;
    question: string;
    missing_fields: MissingField[];
  } | null;
}

// ---------------------------------------------------------------------------
// UI state types
// ---------------------------------------------------------------------------

export interface ClientSummary {
  id: string;           // client_id (MongoDB ObjectId)
  name: string;
  lastActivity: string; // updated_at
  turnCount?: number;
}

export type AgentRunStatus = 'idle' | 'running' | 'done' | 'error';

// ---------------------------------------------------------------------------
// SOA types
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

// ---------------------------------------------------------------------------
// Document & file types
// ---------------------------------------------------------------------------

export interface Attachment {
  id: string;
  name: string;
  type: string;
  size: number;
  url?: string;
  storage_ref?: string;
  uploading?: boolean;
  upload_error?: string;
  facts_summary?: string;
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

// ---------------------------------------------------------------------------
// Backend status
// ---------------------------------------------------------------------------

export type BackendStatus = 'online' | 'offline' | 'connecting';

export interface WorkspaceStatus {
  backend: BackendStatus;
  model: string;
  toolsAvailable: number;
  lastSync?: Date;
}

// ---------------------------------------------------------------------------
// Orchestrator (finobi-style) types
// ---------------------------------------------------------------------------

/** Phase machine states for the AI bar orchestrator */
export type OrchestratorPhase =
  | 'idle'
  | 'planning'
  | 'confirming'
  | 'executing'
  | 'complete'
  | 'error'
  | 'clarifying';

/** A single tool call step in a plan */
export interface OrchestratorToolStep {
  tool_id: string;
  parameters: Record<string, unknown>;
}

/** The plan returned by the backend planner */
export interface OrchestratorPlan {
  type: 'confirmation_required' | 'qna_answer' | 'clarification_needed' | 'no_plan';
  explanation?: string;
  step_labels: string[];
  steps: OrchestratorToolStep[];
  question?: string;
  options?: string[];
  message?: string;
}

/** Result of executing a single tool step */
export interface OrchestratorStepResult {
  tool_id: string;
  step_index: number;
  label: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  result?: Record<string, unknown> | unknown[] | string | null;
  error?: string | null;
  duration_ms?: number;
}

/** A message in the orchestrator conversation history */
export interface ThreadMessage {
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
}

/** Context sent with every planner request */
export interface PageContext {
  currentPage: string;
  selectedClientId?: string;
  selectedClientName?: string;
}

// ---------------------------------------------------------------------------
// Client AI Memory types
// ---------------------------------------------------------------------------

export type MemoryCategory =
  | 'profile'
  | 'employment-income'
  | 'financial-position'
  | 'insurance'
  | 'goals-risk-profile'
  | 'tax-structures'
  | 'estate-planning'
  | 'health'
  | 'interactions';

export interface MemorySource {
  filename: string;
  date: string;
  fact_count: number;
}

export interface ClientMemoryDoc {
  client_id: string;
  category: MemoryCategory;
  category_label: string;
  content: string;
  last_updated?: string;
  fact_count: number;
  sources: MemorySource[];
}

export interface ClientMemoriesResponse {
  client_id: string;
  memories: ClientMemoryDoc[];
}

export interface MemoryEnrichResponse {
  updated_categories: string[];
  facts_extracted: number;
  filename?: string;
  source?: string;
}

/** One persisted orchestrator analysis summary (MongoDB client_analysis_outputs) */
export interface ClientAnalysisOutput {
  id: string;
  client_id: string;
  instruction: string;
  tool_ids: string[];
  step_labels: string[];
  content: string;
  /** manual = AI bar / adviser; automated = goals & objectives workflow */
  source?: 'manual' | 'automated';
  created_at: string;
  updated_at: string;
}

export interface ClientAnalysisOutputsResponse {
  client_id: string;
  outputs: ClientAnalysisOutput[];
}

// ---------------------------------------------------------------------------
// Missing field / tool-input build types
// ---------------------------------------------------------------------------

/** A single critical field that is missing from the client's data */
export interface MissingFieldDef {
  path: string;       // path inside the tool input (e.g. "member.age")
  canonical: string;  // canonical fact path (e.g. "personal.age")
  label: string;      // human-readable label (e.g. "Client Age (years)")
  input_type: 'number' | 'text' | 'boolean';
}

/** Frozen execution state stored when a tool run pauses for missing data */
export interface PendingResume {
  steps: OrchestratorToolStep[];
  step_labels: string[];
  pausedAtIndex: number;
  priorStepResults: Array<{
    tool_id: string;
    step_index: number;
    label: string;
    status: 'completed' | 'failed';
    result: unknown;
    error: string | null;
    duration_ms: number;
  }>;
  instruction: string;
  messages: Array<{ role: string; content: string }>;
  // The field currently being asked (head of pendingMissingFields)
  currentMissingField: MissingFieldDef;
  // Missing fields still to collect (tail)
  pendingMissingFields: MissingFieldDef[];
  collectedOverrides: Record<string, unknown>; // canonical_path → value
}
