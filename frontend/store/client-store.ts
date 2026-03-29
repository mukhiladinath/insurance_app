/**
 * client-store.ts — Zustand store for client management.
 *
 * Clients are stored in the `clients` MongoDB collection, keyed by client_id.
 * Each client has a workspace (client_workspaces) and a factfind (factfinds).
 */

import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';
import * as api from '../lib/api';
import type {
  ClientFacts,
  ClientSummary,
  ClientWorkspace,
  ConversationDocument,
  WorkspaceStatus,
} from '../lib/types';

type AppView = 'dashboard' | 'profile';

/** Used to diff form snapshot vs workspace so we PATCH clears (null) as well as updates. */
function isFactEmpty(v: unknown): boolean {
  if (v === undefined || v === null || v === '') return true;
  if (Array.isArray(v) && v.length === 0) return true;
  return false;
}

function factValueFingerprint(v: unknown): string {
  if (isFactEmpty(v)) return '';
  if (typeof v === 'boolean') return v ? 'b:1' : 'b:0';
  if (typeof v === 'number')
    return Number.isFinite(v) ? `n:${v}` : `j:${JSON.stringify(v)}`;
  if (typeof v === 'string') return `s:${v}`;
  if (Array.isArray(v)) return `a:${JSON.stringify(v)}`;
  return `j:${JSON.stringify(v)}`;
}

function factFieldChanged(prev: unknown, next: unknown): boolean {
  return factValueFingerprint(prev) !== factValueFingerprint(next);
}

interface ClientStore {
  // ---- Navigation ----
  currentView: AppView;

  // ---- Client list ----
  clients: ClientSummary[];
  isLoadingClients: boolean;

  // ---- Active client ----
  activeClientId: string | null;         // MongoDB client _id
  activeClientName: string;
  activeWorkspace: ClientWorkspace | null;
  isLoadingWorkspace: boolean;
  workspaceError: string | null;

  // ---- Documents for active client ----
  activeDocuments: ConversationDocument[];
  isLoadingDocuments: boolean;

  // ---- Backend status ----
  backendStatus: WorkspaceStatus;

  // ---- Actions ----
  loadClients: () => Promise<void>;
  selectClient: (id: string, name: string) => void;
  goToDashboard: () => void;
  loadWorkspace: (clientId: string) => Promise<void>;
  loadDocuments: (clientId: string) => Promise<void>;
  createNewClient: (name: string) => Promise<void>;
  deleteClient: (id: string) => Promise<void>;
  refreshBackendStatus: () => Promise<void>;

  // Called by agent-store after a run to refresh workspace data
  refreshWorkspaceAfterRun: (clientId: string) => Promise<void>;

  // Manually update client_facts fields and refresh workspace
  updateFacts: (clientId: string, facts: Record<string, Record<string, unknown>>) => Promise<void>;

  // Signal to open Fact Find at a specific section (set by AIBar/workspace panel)
  pendingFactFindSection: string | null;
  requestFactFind: (section?: string) => void;
  clearFactFindRequest: () => void;
}

export const useClientStore = create<ClientStore>()(
  persist(
    (set, get) => ({
  currentView: 'dashboard',
  clients: [],
  isLoadingClients: false,

  activeClientId: null,
  activeClientName: '',
  activeWorkspace: null,
  isLoadingWorkspace: false,
  workspaceError: null,

  activeDocuments: [],
  isLoadingDocuments: false,

  backendStatus: { backend: 'connecting', model: 'Insurance AI', toolsAvailable: 0 },
  pendingFactFindSection: null,

  // ---- Load all clients ----
  loadClients: async () => {
    set({ isLoadingClients: true });
    try {
      const clients = await api.listClients();
      const summaries: ClientSummary[] = clients.map((c) => ({
        id: c.id,
        name: c.name,
        lastActivity: c.updated_at,
      }));
      set({ clients: summaries, isLoadingClients: false });
    } catch (err) {
      console.error('loadClients failed:', err);
      set({ isLoadingClients: false });
    }
  },

  // ---- Select an existing client and navigate to their profile ----
  selectClient: (id, name) => {
    set({
      activeClientId: id,
      activeClientName: name,
      currentView: 'profile',
      activeWorkspace: null,
      workspaceError: null,
      activeDocuments: [],
    });
    // Workspace/documents: ClientProfile useEffect when activeClientId is set (incl. after persist rehydrate).
  },

  goToDashboard: () => {
    set({ currentView: 'dashboard', activeClientId: null, activeClientName: '', activeWorkspace: null });
  },

  // ---- Load workspace data for a client ----
  loadWorkspace: async (clientId) => {
    set({ isLoadingWorkspace: true, workspaceError: null });
    try {
      const workspace = await api.getWorkspace(clientId);
      set({ activeWorkspace: workspace, isLoadingWorkspace: false });
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to load workspace';
      set({
        activeWorkspace: null,
        isLoadingWorkspace: false,
        workspaceError: msg.includes('404') ? null : msg,
      });
    }
  },

  // ---- Load documents for the active client ----
  loadDocuments: async (clientId) => {
    if (!clientId) {
      set({ activeDocuments: [], isLoadingDocuments: false });
      return;
    }
    set({ isLoadingDocuments: true });
    try {
      const docs = await api.listWorkspaceDocuments(clientId);
      set({ activeDocuments: docs, isLoadingDocuments: false });
    } catch {
      set({ activeDocuments: [], isLoadingDocuments: false });
    }
  },

  // ---- Create a new client eagerly on the backend ----
  createNewClient: async (name) => {
    // Navigate immediately so the profile page is visible with the loading state
    set({
      currentView: 'profile',
      activeClientId: null,
      activeClientName: name,
      activeWorkspace: null,
      workspaceError: null,
      activeDocuments: [],
      isLoadingWorkspace: true,
    });

    try {
      const client = await api.createClient(name);
      set({ activeClientId: client.id });
      get().loadClients();
      // Workspace/documents loaded by ClientProfile when activeClientId updates
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to create client';
      set({ isLoadingWorkspace: false, workspaceError: msg });
    }
  },

  // ---- Archive (soft-delete) a client ----
  deleteClient: async (id) => {
    try {
      await api.archiveClient(id);
      set((state) => ({
        clients: state.clients.filter((c) => c.id !== id),
        ...(state.activeClientId === id
          ? { activeClientId: null, currentView: 'dashboard' as AppView }
          : {}),
      }));
    } catch (err) {
      console.error('deleteClient failed:', err);
    }
  },

  // ---- Refresh workspace after an agent run ----
  refreshWorkspaceAfterRun: async (clientId) => {
    try {
      const workspace = await api.getWorkspace(clientId);
      set({ activeWorkspace: workspace });
      // Refresh client list and documents
      get().loadClients();
      get().loadDocuments(clientId);
    } catch {
      // non-fatal
    }
  },

  // ---- Fact Find navigation requests ----
  requestFactFind: (section) => set({ pendingFactFindSection: section ?? 'personal' }),
  clearFactFindRequest: () => set({ pendingFactFindSection: null }),

  // ---- Manually update facts (from FactFind form save) ----
  updateFacts: async (clientId, facts) => {
    const prev = get().activeWorkspace?.client_facts;
    const changes: Record<string, unknown> = {};
    for (const [section, fields] of Object.entries(facts)) {
      const prevSection = prev?.[section as keyof ClientFacts] as
        | Record<string, unknown>
        | undefined;
      for (const [fieldName, value] of Object.entries(fields)) {
        const prevVal = prevSection?.[fieldName];
        if (!factFieldChanged(prevVal, value)) continue;
        // Include null so the backend clears the field; omitting the key left old values in MongoDB.
        changes[`${section}.${fieldName}`] = value ?? null;
      }
    }
    if (Object.keys(changes).length === 0) return;

    await api.patchFactfindDirect(clientId, changes);
    try {
      const workspace = await api.getWorkspace(clientId);
      set({ activeWorkspace: workspace });
    } catch {
      // Saved on server; refresh failed — caller can reload profile
    }
  },

  // ---- Backend status ----
  refreshBackendStatus: async () => {
    try {
      const [healthRes, toolsRes] = await Promise.all([api.health(), api.listTools()]);
      set({
        backendStatus: {
          backend: healthRes.status === 'ok' ? 'online' : 'offline',
          model: 'Insurance AI',
          toolsAvailable: toolsRes.length,
          lastSync: new Date(),
        },
      });
    } catch {
      set((s) => ({ backendStatus: { ...s.backendStatus, backend: 'offline' } }));
    }
  },
    }),
    {
      name: 'insurance-app-client',
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        activeClientId: state.activeClientId,
        activeClientName: state.activeClientName,
        currentView: state.currentView,
      }),
    },
  ),
);
