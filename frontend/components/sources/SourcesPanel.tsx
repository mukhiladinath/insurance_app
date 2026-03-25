'use client';

import { useChatStore } from '@/store/chat-store';
import { getDocumentUrl } from '@/lib/api';
import { parseUTCDate } from '@/lib/utils';
import type { ConversationDocument } from '@/lib/types';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function FileIcon({ contentType }: { contentType: string }) {
  if (contentType === 'application/pdf') {
    return (
      <svg className="w-8 h-8 text-red-500 shrink-0" fill="currentColor" viewBox="0 0 24 24">
        <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8l-6-6zm-1 1.5L18.5 9H13V3.5zM9.3 15.5c-.1.3-.3.5-.6.7-.3.1-.6.2-1 .2H7v1.6H6v-4.5h1.7c.4 0 .7.1 1 .2.3.1.5.3.6.6.1.2.2.5.2.7 0 .3-.1.6-.2.8zm3.4.4c-.1.4-.3.7-.5.9-.2.2-.5.4-.8.5-.3.1-.7.1-1 .1H9.3v-4.5h1.1c.4 0 .7 0 1 .1.3.1.6.3.8.5.2.2.4.5.5.9.1.3.1.6.1 1s0 .7-.1 1zm3.3-2.6h-2v1.1h1.8v.8h-1.8v1.9H13v-4.5h3v.7z" />
      </svg>
    );
  }
  if (contentType.includes('word') || contentType.includes('document')) {
    return (
      <svg className="w-8 h-8 text-blue-600 shrink-0" fill="currentColor" viewBox="0 0 24 24">
        <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8l-6-6zm-1 1.5L18.5 9H13V3.5zM7 15l1.5-4.5h1l1 3.2 1-3.2h1L14 15h-1l-1-3.1-1 3.1H7z" />
      </svg>
    );
  }
  if (contentType.startsWith('image/')) {
    return (
      <svg className="w-8 h-8 text-green-500 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 15.75l5.159-5.159a2.25 2.25 0 013.182 0l5.159 5.159m-1.5-1.5l1.409-1.409a2.25 2.25 0 013.182 0l2.909 2.909M3 9.75h.008v.008H3V9.75zm.375 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zM21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    );
  }
  return (
    <svg className="w-8 h-8 text-slate-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Document card
// ---------------------------------------------------------------------------

function DocumentCard({ doc }: { doc: ConversationDocument }) {
  const url = getDocumentUrl(doc.id);
  const uploadedAt = parseUTCDate(doc.created_at).toLocaleString('en-IN', {
    timeZone: 'Asia/Kolkata',
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: true,
  });

  return (
    <div className="flex items-start gap-3 p-3 rounded-lg border border-slate-200 bg-white hover:border-indigo-200 hover:shadow-sm transition-all">
      <FileIcon contentType={doc.content_type} />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-slate-800 truncate" title={doc.filename}>
          {doc.filename}
        </p>
        <p className="text-[11px] text-slate-400 mt-0.5">
          {formatBytes(doc.size_bytes)} · {uploadedAt}
        </p>
        {doc.facts_found && (
          <p className="text-[11px] text-indigo-600 mt-1 truncate" title={doc.facts_summary}>
            Facts: {doc.facts_summary}
          </p>
        )}
      </div>
      <a
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        title="Open document"
        className="shrink-0 flex items-center justify-center w-7 h-7 rounded-md text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 transition-colors"
      >
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 6H5.25A2.25 2.25 0 003 8.25v10.5A2.25 2.25 0 005.25 21h10.5A2.25 2.25 0 0018 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25" />
        </svg>
      </a>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Panel
// ---------------------------------------------------------------------------

export function SourcesPanel() {
  const { isSourcesPanelOpen, conversationDocuments, isLoadingDocuments, closeSourcesPanel } = useChatStore();

  if (!isSourcesPanelOpen) return null;

  return (
    <aside className="flex flex-col h-full w-full border-l border-slate-200 bg-slate-50 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-200 bg-white shrink-0">
        <div className="flex items-center gap-2">
          <svg className="w-4 h-4 text-indigo-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 12.75V12A2.25 2.25 0 014.5 9.75h15A2.25 2.25 0 0121.75 12v.75m-8.69-6.44l-2.12-2.12a1.5 1.5 0 00-1.061-.44H4.5A2.25 2.25 0 002.25 6v12a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18V9a2.25 2.25 0 00-2.25-2.25h-5.379a1.5 1.5 0 01-1.06-.44z" />
          </svg>
          <span className="text-sm font-semibold text-slate-800">Uploaded Documents</span>
          {conversationDocuments.length > 0 && (
            <span className="rounded-full bg-indigo-100 text-indigo-700 text-[10px] font-semibold px-2 py-0.5">
              {conversationDocuments.length}
            </span>
          )}
        </div>
        <button
          onClick={closeSourcesPanel}
          className="text-slate-400 hover:text-slate-600 transition-colors p-1 rounded"
          title="Close"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-3">
        {isLoadingDocuments ? (
          <div className="flex items-center justify-center h-24 gap-2 text-slate-400">
            <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
            </svg>
            <span className="text-xs">Loading documents…</span>
          </div>
        ) : conversationDocuments.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-32 text-center gap-2">
            <svg className="w-8 h-8 text-slate-300" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m6.75 12H9m1.5-12H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
            </svg>
            <p className="text-xs font-medium text-slate-500">No documents uploaded yet</p>
            <p className="text-xs text-slate-400">Upload a file using the Upload File button to get started</p>
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            {conversationDocuments.map((doc) => (
              <DocumentCard key={doc.id} doc={doc} />
            ))}
          </div>
        )}
      </div>
    </aside>
  );
}
