'use client';

import { create } from 'zustand';
import { Chat, Message, Attachment, WorkspaceStatus } from '@/lib/types';
import * as api from '@/lib/api';
import { generateId } from '@/lib/utils';

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

  // — Actions —
  loadConversations: () => Promise<void>;
  setActiveChat: (id: string) => Promise<void>;
  sendMessage: (content: string, attachments?: Attachment[]) => Promise<void>;
  createNewChat: () => void;
  addPendingFile: (file: Attachment) => void;
  removePendingFile: (id: string) => void;
  clearPendingFiles: () => void;
  setSearchQuery: (query: string) => void;
  toggleSidebar: () => void;
  refreshWorkspaceStatus: () => Promise<void>;
}

// ---------------------------------------------------------------------------
// Mappers — API shape → UI shape
// ---------------------------------------------------------------------------

function toChat(c: { id: string; title: string; updated_at: string; last_message_at: string | null }): Chat {
  return {
    id: c.id,
    title: c.title,
    lastMessage: '',
    timestamp: new Date(c.last_message_at ?? c.updated_at),
    messageCount: 0,
  };
}

function toMessage(m: { id: string; role: string; content: string; created_at: string }): Message {
  return {
    id: m.id,
    role: m.role as 'user' | 'assistant',
    content: m.content,
    timestamp: new Date(m.created_at),
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

  // -------------------------------------------------------------------------
  // Load conversations list from backend
  // -------------------------------------------------------------------------
  loadConversations: async () => {
    set({ isLoadingChats: true });
    try {
      const data = await api.listConversations();
      const chats = data.map(toChat);
      set({ chats, isLoadingChats: false });

      // Auto-select first conversation if nothing is active
      if (get().activeChatId === null && chats.length > 0) {
        await get().setActiveChat(chats[0].id);
      }
    } catch {
      set({ isLoadingChats: false });
    }
  },

  // -------------------------------------------------------------------------
  // Select a conversation and load its messages
  // -------------------------------------------------------------------------
  setActiveChat: async (id) => {
    set({ activeChatId: id, isLoadingMessages: true, messages: [] });
    try {
      const data = await api.getMessages(id);
      set({ messages: data.map(toMessage), isLoadingMessages: false });
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
    set({ activeChatId: null, messages: [], pendingFiles: [] });
  },

  // -------------------------------------------------------------------------
  // File attachments
  // -------------------------------------------------------------------------
  addPendingFile: (file) =>
    set((state) => ({ pendingFiles: [...state.pendingFiles, file] })),

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
