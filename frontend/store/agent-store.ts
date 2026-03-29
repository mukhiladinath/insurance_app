/**
 * agent-store.ts — Zustand store for the persistent AI bar + workspace runs.
 *
 * Submits queries to POST /api/workspace/{clientId}/run (new workspace endpoint).
 *
 * State machine:
 *   idle → running (user submits) → done / error
 *   done → idle (user clears or starts new query)
 */

import { create } from 'zustand';
import * as api from '../lib/api';
import type { WorkspaceRunResponse, AgentRunStatus, Attachment } from '../lib/types';
import { USER_ID } from '../lib/api';

interface AgentStore {
  // ---- Input state ----
  inputValue: string;
  pendingFiles: Attachment[];

  // ---- Workspace panel visibility ----
  isWorkspaceOpen: boolean;

  // ---- Current run ----
  status: AgentRunStatus;
  currentRun: WorkspaceRunResponse | null;
  error: string | null;

  // ---- Actions ----
  setInput: (value: string) => void;
  addFile: (attachment: Attachment) => void;
  removeFile: (id: string) => void;
  updateFile: (id: string, update: Partial<Attachment>) => void;

  submitQuery: (clientId: string | null) => Promise<void>;

  openWorkspace: () => void;
  closeWorkspace: () => void;
  clearRun: () => void;
}

export const useAgentStore = create<AgentStore>((set, get) => ({
  inputValue: '',
  pendingFiles: [],
  isWorkspaceOpen: false,
  status: 'idle',
  currentRun: null,
  error: null,

  setInput: (value) => set({ inputValue: value }),

  addFile: (attachment) =>
    set((s) => ({ pendingFiles: [...s.pendingFiles, attachment] })),

  removeFile: (id) =>
    set((s) => ({ pendingFiles: s.pendingFiles.filter((f) => f.id !== id) })),

  updateFile: (id, update) =>
    set((s) => ({
      pendingFiles: s.pendingFiles.map((f) => (f.id === id ? { ...f, ...update } : f)),
    })),

  submitQuery: async (clientId) => {
    const { inputValue, pendingFiles } = get();
    const message = inputValue.trim();
    if (!message || !clientId) return;

    set({ status: 'running', isWorkspaceOpen: true, error: null, currentRun: null, inputValue: '' });

    const attachedFiles = pendingFiles
      .filter((f) => f.storage_ref)
      .map((f) => ({
        filename: f.name,
        content_type: f.type,
        size_bytes: f.size,
        storage_ref: f.storage_ref!,
      }));

    try {
      const response = await api.runWorkspace(clientId, {
        user_id: USER_ID,
        message,
        attached_files: attachedFiles,
      });

      set({ status: 'done', currentRun: response, pendingFiles: [] });
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Agent run failed';
      set({ status: 'error', error: msg });
    }
  },

  openWorkspace: () => set({ isWorkspaceOpen: true }),
  closeWorkspace: () => set({ isWorkspaceOpen: false }),
  clearRun: () => set({ status: 'idle', currentRun: null, error: null, isWorkspaceOpen: false }),
}));
