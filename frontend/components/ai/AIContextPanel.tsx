'use client';

/**
 * AIContextPanel — Client AI Memory management UI.
 *
 * Mirrors finobi's ai-context page. Shows:
 *   - 9 category memory tabs (Profile, Employment, Financial, Insurance, etc.)
 *   - Document upload to enrich memory
 *   - Sync from Fact Find button
 *
 * Uses /api/client-context/* backend routes.
 */

import { useState, useEffect, useRef } from 'react';
import {
  Brain, Upload, RefreshCw, Loader2, FileText,
  ChevronDown, ChevronRight, AlertCircle, Check, Pencil, Save, X,
} from 'lucide-react';
import MarkdownProse from '../ui/MarkdownProse';
import type { ClientMemoryDoc, ClientMemoriesResponse, MemoryEnrichResponse } from '../../lib/types';

const BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

// ---------------------------------------------------------------------------
// Category metadata
// ---------------------------------------------------------------------------

const CATEGORY_ORDER = [
  'profile',
  'employment-income',
  'financial-position',
  'insurance',
  'goals-risk-profile',
  'tax-structures',
  'estate-planning',
  'health',
  'interactions',
] as const;

const CATEGORY_ICONS: Record<string, string> = {
  'profile':           '👤',
  'employment-income': '💼',
  'financial-position':'💰',
  'insurance':         '🛡️',
  'goals-risk-profile':'🎯',
  'tax-structures':    '🏛️',
  'estate-planning':   '📋',
  'health':            '❤️',
  'interactions':      '💬',
};

// ---------------------------------------------------------------------------
// API helpers
// ---------------------------------------------------------------------------

async function fetchMemories(clientId: string): Promise<ClientMemoriesResponse> {
  const res = await fetch(`${BASE}/api/client-context/${clientId}/memories`);
  if (!res.ok) throw new Error(`Failed to load memories (${res.status})`);
  return res.json();
}

async function uploadAndEnrich(clientId: string, file: File): Promise<MemoryEnrichResponse> {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch(`${BASE}/api/client-context/${clientId}/upload-enrich`, {
    method: 'POST',
    body: form,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err?.detail ?? `Upload failed (${res.status})`);
  }
  return res.json();
}

async function syncFromFactfind(clientId: string): Promise<MemoryEnrichResponse> {
  const res = await fetch(`${BASE}/api/client-context/${clientId}/enrich-from-factfind`, {
    method: 'POST',
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err?.detail ?? `Sync failed (${res.status})`);
  }
  return res.json();
}

async function putMemoryCategory(
  clientId: string,
  category: string,
  content: string,
): Promise<ClientMemoryDoc> {
  const res = await fetch(`${BASE}/api/client-context/${clientId}/memories/${category}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err?.detail ?? `Save failed (${res.status})`);
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// Memory category tab
// ---------------------------------------------------------------------------

function MemoryCategoryTab({
  doc,
  isActive,
  onClick,
}: {
  doc: ClientMemoryDoc;
  isActive: boolean;
  onClick: () => void;
}) {
  const icon = CATEGORY_ICONS[doc.category] ?? '📄';
  return (
    <button
      onClick={onClick}
      className={`w-full flex items-center gap-2.5 px-3 py-2.5 text-left rounded-lg transition-colors text-sm ${
        isActive
          ? 'bg-indigo-50 text-indigo-700 font-medium border border-indigo-100'
          : 'text-slate-600 hover:bg-slate-50'
      }`}
    >
      <span className="text-base leading-none">{icon}</span>
      <div className="flex-1 min-w-0">
        <p className="truncate">{doc.category_label}</p>
        {doc.fact_count > 0 && (
          <p className="text-xs text-slate-400">{doc.fact_count} fact{doc.fact_count !== 1 ? 's' : ''}</p>
        )}
      </div>
    </button>
  );
}

// ---------------------------------------------------------------------------
// Source attribution
// ---------------------------------------------------------------------------

function SourceList({ sources }: { sources: ClientMemoryDoc['sources'] }) {
  const [open, setOpen] = useState(false);
  if (!sources || sources.length === 0) return null;

  return (
    <div className="mt-4 border-t border-slate-100 pt-3">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1 text-xs text-slate-400 hover:text-slate-600 transition-colors"
      >
        {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        {sources.length} source{sources.length !== 1 ? 's' : ''}
      </button>
      {open && (
        <ul className="mt-2 space-y-1">
          {sources.map((s, i) => (
            <li key={i} className="flex items-center gap-2 text-xs text-slate-400">
              <FileText size={11} className="flex-shrink-0" />
              <span className="truncate">{s.filename}</span>
              <span className="text-slate-300">·</span>
              <span>{s.date}</span>
              {s.fact_count > 0 && <span>· {s.fact_count} facts</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

interface Props {
  clientId: string;
}

export default function AIContextPanel({ clientId }: Props) {
  const [memories, setMemories] = useState<ClientMemoryDoc[]>([]);
  const [activeCategory, setActiveCategory] = useState<string>('profile');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [lastEnrich, setLastEnrich] = useState<MemoryEnrichResponse | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [draftContent, setDraftContent] = useState('');
  const [savingMemory, setSavingMemory] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadMemories = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchMemories(clientId);
      // Sort by canonical order
      const sorted = [...data.memories].sort((a, b) => {
        const ai = CATEGORY_ORDER.indexOf(a.category as typeof CATEGORY_ORDER[number]);
        const bi = CATEGORY_ORDER.indexOf(b.category as typeof CATEGORY_ORDER[number]);
        return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
      });
      setMemories(sorted);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load memory');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (clientId) loadMemories();
  }, [clientId]);

  const handleFileSelect = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    setUploading(true);
    setLastEnrich(null);
    try {
      for (const file of Array.from(files)) {
        const result = await uploadAndEnrich(clientId, file);
        setLastEnrich(result);
      }
      await loadMemories();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setUploading(false);
    }
  };

  const handleSyncFactfind = async () => {
    setSyncing(true);
    setLastEnrich(null);
    try {
      const result = await syncFromFactfind(clientId);
      setLastEnrich(result);
      await loadMemories();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sync failed');
    } finally {
      setSyncing(false);
    }
  };

  const activeDoc = memories.find((m) => m.category === activeCategory);

  useEffect(() => {
    setIsEditing(false);
    setDraftContent('');
  }, [activeCategory]);

  const startEditMemory = () => {
    if (!activeDoc) return;
    setDraftContent(activeDoc.content);
    setIsEditing(true);
  };

  const cancelEditMemory = () => {
    setIsEditing(false);
    setDraftContent('');
  };

  const saveEditMemory = async () => {
    if (!activeDoc) return;
    setSavingMemory(true);
    setError(null);
    try {
      const updated = await putMemoryCategory(clientId, activeDoc.category, draftContent);
      setMemories((prev) => prev.map((m) => (m.category === updated.category ? updated : m)));
      setIsEditing(false);
      setDraftContent('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed');
    } finally {
      setSavingMemory(false);
    }
  };

  return (
    <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
      {/* Header */}
      <div className="px-5 py-3 bg-slate-50 border-b border-slate-100 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Brain size={15} className="text-indigo-500" />
          <h3 className="text-xs font-semibold text-slate-600 uppercase tracking-wider">AI Memory</h3>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleSyncFactfind}
            disabled={syncing || uploading}
            className="flex items-center gap-1.5 px-2.5 py-1 text-xs bg-white border border-slate-200 text-slate-600 rounded-lg hover:bg-slate-50 transition-colors disabled:opacity-50"
          >
            {syncing ? <Loader2 size={11} className="animate-spin" /> : <RefreshCw size={11} />}
            Sync Fact Find
          </button>
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading || syncing}
            className="flex items-center gap-1.5 px-2.5 py-1 text-xs bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors disabled:opacity-50"
          >
            {uploading ? <Loader2 size={11} className="animate-spin" /> : <Upload size={11} />}
            Upload Document
          </button>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept=".pdf,.docx,.png,.jpg,.jpeg,.webp,.txt,.csv"
            className="hidden"
            onChange={(e) => handleFileSelect(e.target.files)}
          />
          <button
            onClick={loadMemories}
            disabled={loading}
            className="p-1.5 text-slate-400 hover:text-slate-700 hover:bg-slate-100 rounded-lg transition-colors disabled:opacity-50"
          >
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {/* Enrich success notice */}
      {lastEnrich && lastEnrich.updated_categories.length > 0 && (
        <div className="px-5 py-2 bg-emerald-50 border-b border-emerald-100 flex items-center gap-2">
          <Check size={13} className="text-emerald-500 flex-shrink-0" />
          <p className="text-xs text-emerald-700">
            {lastEnrich.facts_extracted > 0
              ? `Extracted ${lastEnrich.facts_extracted} facts → updated ${lastEnrich.updated_categories.join(', ')}`
              : `Synced ${lastEnrich.updated_categories.join(', ')}`}
          </p>
        </div>
      )}

      {/* Error notice */}
      {error && (
        <div className="px-5 py-2 bg-red-50 border-b border-red-100 flex items-center gap-2">
          <AlertCircle size={13} className="text-red-500 flex-shrink-0" />
          <p className="text-xs text-red-700">{error}</p>
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-12 text-slate-400 gap-2">
          <Loader2 size={18} className="animate-spin" />
          <span className="text-sm">Loading memory…</span>
        </div>
      ) : (
        <div className="flex">
          {/* Category sidebar */}
          <div className="w-52 flex-shrink-0 border-r border-slate-100 p-2 space-y-0.5">
            {memories.map((doc) => (
              <MemoryCategoryTab
                key={doc.category}
                doc={doc}
                isActive={doc.category === activeCategory}
                onClick={() => setActiveCategory(doc.category)}
              />
            ))}
            {memories.length === 0 && (
              <p className="text-xs text-slate-400 px-3 py-2">No memory yet</p>
            )}
          </div>

          {/* Content pane */}
          <div className="flex-1 min-w-0 p-5">
            {activeDoc ? (
              <>
                <div className="flex items-center justify-between gap-2 mb-4">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="text-xl">{CATEGORY_ICONS[activeDoc.category] ?? '📄'}</span>
                    <div>
                      <h4 className="text-sm font-semibold text-slate-800">{activeDoc.category_label}</h4>
                      {activeDoc.last_updated && (
                        <p className="text-xs text-slate-400">
                          Last updated: {new Date(activeDoc.last_updated).toLocaleDateString()}
                        </p>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-1 flex-shrink-0">
                    {isEditing ? (
                      <>
                        <button
                          type="button"
                          onClick={cancelEditMemory}
                          disabled={savingMemory}
                          className="inline-flex items-center gap-1 px-2 py-1 text-xs border border-slate-200 rounded-lg text-slate-600 hover:bg-slate-50 disabled:opacity-50"
                        >
                          <X size={12} /> Cancel
                        </button>
                        <button
                          type="button"
                          onClick={saveEditMemory}
                          disabled={savingMemory}
                          className="inline-flex items-center gap-1 px-2 py-1 text-xs bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50"
                        >
                          {savingMemory ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
                          Save
                        </button>
                      </>
                    ) : (
                      <button
                        type="button"
                        onClick={startEditMemory}
                        className="inline-flex items-center gap-1 px-2 py-1 text-xs border border-slate-200 rounded-lg text-slate-600 hover:bg-slate-50"
                      >
                        <Pencil size={12} /> Edit
                      </button>
                    )}
                  </div>
                </div>
                {isEditing ? (
                  <textarea
                    value={draftContent}
                    onChange={(e) => setDraftContent(e.target.value)}
                    className="w-full min-h-[240px] text-sm font-mono text-slate-800 border border-slate-200 rounded-lg p-3 focus:outline-none focus:ring-2 focus:ring-indigo-200"
                    spellCheck={false}
                  />
                ) : (
                  <MarkdownProse content={activeDoc.content} />
                )}
                <SourceList sources={activeDoc.sources} />
              </>
            ) : (
              <div className="flex items-center justify-center h-32 text-slate-400 text-sm">
                Select a category from the left
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
