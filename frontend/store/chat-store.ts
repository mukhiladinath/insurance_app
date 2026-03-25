'use client';

import { create } from 'zustand';
import { Chat, Message, Attachment, WorkspaceStatus, SOASection, SOAMissingQuestion, SOADraftPayload, ConversationDocument } from '@/lib/types';
import * as api from '@/lib/api';
import { generateId, parseUTCDate } from '@/lib/utils';

// ---------------------------------------------------------------------------
// Store shape
// ---------------------------------------------------------------------------

interface ChatStore {
  // — State —
  chats: Chat[];
  activeChatId: string | null;
  messages: Message[];
  isStreaming: boolean;
  pendingFiles: Attachment[];
  searchQuery: string;
  isSidebarOpen: boolean;
  workspaceStatus: WorkspaceStatus;
  isLoadingChats: boolean;
  isLoadingMessages: boolean;

  // — Sources panel state —
  isSourcesPanelOpen: boolean;
  conversationDocuments: ConversationDocument[];
  isLoadingDocuments: boolean;

  // — SOA panel state —
  isSOAPanelOpen: boolean;
  isSOAMaximized: boolean;
  soaSections: SOASection[];
  soaMissingQuestions: SOAMissingQuestion[];
  isSOAGenerating: boolean;

  // — Actions —
  loadConversations: () => Promise<void>;
  setActiveChat: (id: string) => Promise<void>;
  sendMessage: (content: string, attachments?: Attachment[]) => Promise<void>;
  createNewChat: () => void;
  deleteChat: (id: string) => Promise<void>;
  addPendingFile: (file: Attachment) => void;
  uploadAndAddFile: (file: File) => Promise<void>;
  removePendingFile: (id: string) => void;
  clearPendingFiles: () => void;
  setSearchQuery: (query: string) => void;
  toggleSidebar: () => void;
  refreshWorkspaceStatus: () => Promise<void>;

  // — Sources panel actions —
  openSourcesPanel: () => Promise<void>;
  closeSourcesPanel: () => void;

  // — SOA panel actions —
  openSOAPanel: (payload: SOADraftPayload) => void;
  closeSOAPanel: () => void;
  toggleSOAMaximize: () => void;
  generateSOAForConversation: () => Promise<void>;
  submitSOAAnswers: (answers: Record<string, string>) => Promise<void>;
}

// ---------------------------------------------------------------------------
// Mappers — API shape → UI shape
// ---------------------------------------------------------------------------

function toChat(c: { id: string; title: string; updated_at: string; last_message_at: string | null }): Chat {
  return {
    id: c.id,
    title: c.title,
    lastMessage: '',
    timestamp: parseUTCDate(c.last_message_at ?? c.updated_at),
    messageCount: 0,
  };
}

function toMessage(m: { id: string; role: string; content: string; created_at: string }): Message {
  return {
    id: m.id,
    role: m.role as 'user' | 'assistant',
    content: m.content,
    timestamp: parseUTCDate(m.created_at),
  };
}

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

export const useChatStore = create<ChatStore>((set, get) => ({
  chats: [],
  activeChatId: null,
  messages: [],
  isStreaming: false,
  pendingFiles: [],
  searchQuery: '',
  isSidebarOpen: true,
  workspaceStatus: { backend: 'connecting', model: 'Insurance AI', toolsAvailable: 0 },
  isLoadingChats: false,
  isLoadingMessages: false,

  isSourcesPanelOpen: false,
  conversationDocuments: [],
  isLoadingDocuments: false,

  isSOAPanelOpen: false,
  isSOAMaximized: false,
  soaSections: [],
  soaMissingQuestions: [],
  isSOAGenerating: false,

  // -------------------------------------------------------------------------
  // Load conversations list from backend
  // -------------------------------------------------------------------------
  loadConversations: async () => {
    set({ isLoadingChats: true });
    try {
      const data = await api.listConversations();
      const chats = data.map(toChat);
      set({ chats, isLoadingChats: false });

      // Restore the chat that was open before the page refresh (sessionStorage survives
      // refresh but is cleared when the tab is closed / a new session starts).
      const savedId = typeof window !== 'undefined' ? sessionStorage.getItem('activeChatId') : null;
      if (savedId && chats.some((c) => c.id === savedId)) {
        await get().setActiveChat(savedId);
      }
      // Otherwise stay on the new-chat screen (activeChatId remains null)
    } catch {
      set({ isLoadingChats: false });
    }
  },

  // -------------------------------------------------------------------------
  // Select a conversation and load its messages
  // -------------------------------------------------------------------------
  setActiveChat: async (id) => {
    if (typeof window !== 'undefined') sessionStorage.setItem('activeChatId', id);
    set({ activeChatId: id, isLoadingMessages: true, messages: [], isSOAPanelOpen: false, soaSections: [], soaMissingQuestions: [], isSourcesPanelOpen: false, conversationDocuments: [] });
    try {
      const [messages, soaDraft] = await Promise.allSettled([
        api.getMessages(id),
        api.getSOADraft(id),
      ]);

      set({ messages: messages.status === 'fulfilled' ? messages.value.map(toMessage) : [], isLoadingMessages: false });

      if (soaDraft.status === 'fulfilled') {
        get().openSOAPanel({ type: 'soa_draft', ...soaDraft.value });
      }
    } catch {
      set({ isLoadingMessages: false });
    }
  },

  // -------------------------------------------------------------------------
  // Send a message — optimistic update + backend call
  // -------------------------------------------------------------------------
  sendMessage: async (content, attachments) => {
    const tempId = generateId();

    // Optimistic: show user message immediately
    set((state) => ({
      messages: [
        ...state.messages,
        {
          id: tempId,
          role: 'user' as const,
          content,
          timestamp: new Date(),
          attachments,
        },
      ],
      isStreaming: true,
      pendingFiles: [],
    }));

    try {
      const response = await api.sendMessage({
        user_id: api.USER_ID,
        conversation_id: get().activeChatId ?? undefined,
        message: content,
        attached_files: attachments?.map((a) => ({
          filename: a.name,
          content_type: a.type,
          size_bytes: a.size,
          storage_ref: a.storage_ref,
        })),
      });

      // Replace optimistic user message with real one; append assistant reply
      set((state) => ({
        activeChatId: response.conversation.id,
        isStreaming: false,
        messages: [
          ...state.messages.filter((m) => m.id !== tempId),
          toMessage(response.user_message),
          toMessage(response.assistant_message),
        ],
      }));

      // Open SOA panel if this response contains a SOA draft
      const payload = response.assistant_message.structured_payload;
      if (payload && (payload as Record<string, unknown>)['type'] === 'soa_draft') {
        get().openSOAPanel(payload as unknown as SOADraftPayload);
      }

      // Upsert conversation in sidebar list (move to top with updated title)
      const updatedChat: Chat = {
        id: response.conversation.id,
        title: response.conversation.title,
        lastMessage: response.assistant_message.content.slice(0, 120),
        timestamp: new Date(response.conversation.updated_at),
        messageCount: 0,
      };
      set((state) => ({
        chats: [
          updatedChat,
          ...state.chats.filter((c) => c.id !== response.conversation.id),
        ],
      }));
    } catch {
      // Remove optimistic message; show inline error from assistant
      set((state) => ({
        isStreaming: false,
        messages: [
          ...state.messages.filter((m) => m.id !== tempId),
          {
            id: generateId(),
            role: 'assistant' as const,
            content:
              'Sorry, I could not reach the backend. Please make sure the server is running and try again.',
            timestamp: new Date(),
          },
        ],
      }));
    }
  },

  // -------------------------------------------------------------------------
  // Start a new chat (local only — conversation created on first message)
  // -------------------------------------------------------------------------
  createNewChat: () => {
    if (typeof window !== 'undefined') sessionStorage.removeItem('activeChatId');
    set({ activeChatId: null, messages: [], pendingFiles: [] });
  },

  deleteChat: async (id) => {
    // Optimistic: remove from UI immediately
    set((state) => {
      const remaining = state.chats.filter((c) => c.id !== id);
      const wasActive = state.activeChatId === id;
      if (wasActive && typeof window !== 'undefined') sessionStorage.removeItem('activeChatId');
      return {
        chats: remaining,
        activeChatId: wasActive ? null : state.activeChatId,
        messages: wasActive ? [] : state.messages,
        isSOAPanelOpen: wasActive ? false : state.isSOAPanelOpen,
        soaSections: wasActive ? [] : state.soaSections,
        soaMissingQuestions: wasActive ? [] : state.soaMissingQuestions,
      };
    });
    // Fire-and-forget backend delete — UI already updated
    api.deleteConversation(id).catch(() => {/* non-fatal */});
  },

  // -------------------------------------------------------------------------
  // File attachments
  // -------------------------------------------------------------------------
  addPendingFile: (file) =>
    set((state) => ({ pendingFiles: [...state.pendingFiles, file] })),

  // Upload file to backend, track uploading state, store storage_ref on completion
  uploadAndAddFile: async (file: File) => {
    const tempId = generateId();

    // Add file immediately with uploading=true so UI can show a spinner
    const attachment: Attachment = {
      id: tempId,
      name: file.name,
      type: file.type,
      size: file.size,
      uploading: true,
    };
    set((state) => ({ pendingFiles: [...state.pendingFiles, attachment] }));

    try {
      const result = await api.uploadFile(file, api.USER_ID, get().activeChatId);

      // Update attachment with storage_ref and facts_summary
      set((state) => ({
        pendingFiles: state.pendingFiles.map((f) =>
          f.id === tempId
            ? {
                ...f,
                uploading: false,
                storage_ref: result.storage_ref,
                facts_summary: result.facts_found ? result.facts_summary : undefined,
              }
            : f,
        ),
      }));
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Upload failed';
      // Mark as error but keep in list so user can see and remove it
      set((state) => ({
        pendingFiles: state.pendingFiles.map((f) =>
          f.id === tempId ? { ...f, uploading: false, upload_error: message } : f,
        ),
      }));
    }
  },

  removePendingFile: (id) =>
    set((state) => ({
      pendingFiles: state.pendingFiles.filter((f) => f.id !== id),
    })),

  clearPendingFiles: () => set({ pendingFiles: [] }),

  // -------------------------------------------------------------------------
  // Search / UI
  // -------------------------------------------------------------------------
  setSearchQuery: (query) => set({ searchQuery: query }),

  toggleSidebar: () =>
    set((state) => ({ isSidebarOpen: !state.isSidebarOpen })),

  // -------------------------------------------------------------------------
  // SOA panel
  // -------------------------------------------------------------------------
  openSourcesPanel: async () => {
    const conversationId = get().activeChatId;
    if (!conversationId) {
      set({ isSourcesPanelOpen: true, conversationDocuments: [], isLoadingDocuments: false });
      return;
    }
    set({ isSourcesPanelOpen: true, isLoadingDocuments: true });
    try {
      const docs = await api.listDocuments(conversationId);
      set({ conversationDocuments: docs, isLoadingDocuments: false });
    } catch {
      set({ isLoadingDocuments: false });
    }
  },

  closeSourcesPanel: () => set({ isSourcesPanelOpen: false }),

  openSOAPanel: (payload) => set({
    isSOAPanelOpen: true,
    soaSections: payload.sections,
    soaMissingQuestions: payload.missing_questions,
  }),

  closeSOAPanel: () => set({ isSOAPanelOpen: false, isSOAMaximized: false }),

  toggleSOAMaximize: () => set((state) => ({ isSOAMaximized: !state.isSOAMaximized })),

  generateSOAForConversation: async () => {
    const conversationId = get().activeChatId;
    if (!conversationId) return;

    // If sections are already loaded just show the panel — no need to regenerate
    if (get().soaSections.length > 0) {
      set({ isSOAPanelOpen: true });
      return;
    }

    set({ isSOAGenerating: true, isSOAPanelOpen: true });
    try {
      const result = await api.generateSOA(conversationId);
      set({
        soaSections: result.sections,
        soaMissingQuestions: result.missing_questions,
        isSOAGenerating: false,
      });
    } catch {
      set({ isSOAGenerating: false });
    }
  },

  submitSOAAnswers: async (answers) => {
    const conversationId = get().activeChatId;
    if (!conversationId) return;
    set({ isSOAGenerating: true });
    try {
      const result = await api.generateSOA(conversationId, answers);
      set({
        soaSections: result.sections,
        soaMissingQuestions: result.missing_questions,
        isSOAGenerating: false,
      });
    } catch {
      set({ isSOAGenerating: false });
    }
  },

  // -------------------------------------------------------------------------
  // Workspace status — polls /api/health and /api/tools
  // -------------------------------------------------------------------------
  refreshWorkspaceStatus: async () => {
    try {
      const [healthData, tools] = await Promise.all([
        api.health(),
        api.listTools(),
      ]);
      set({
        workspaceStatus: {
          backend: healthData.status === 'ok' ? 'online' : 'offline',
          model: 'finobi-4o-mini',
          toolsAvailable: tools.length,
          lastSync: new Date(),
        },
      });
    } catch {
      set((state) => ({
        workspaceStatus: { ...state.workspaceStatus, backend: 'offline' },
      }));
    }
  },
}));
