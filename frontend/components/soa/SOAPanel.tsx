'use client';

import { useState, useRef, useEffect } from 'react';
import { useChatStore } from '@/store/chat-store';
import { TipTapEditor } from './TipTapEditor';
import type { SOAMissingQuestion } from '@/lib/types';
import { downloadSOAasPDF, downloadSOAasWord } from '@/lib/soa-download';

// ---------------------------------------------------------------------------
// Missing-field answer form
// ---------------------------------------------------------------------------

function MissingFieldsForm({
  questions,
  onSubmit,
  isSubmitting,
}: {
  questions: SOAMissingQuestion[];
  onSubmit: (answers: Record<string, string>) => void;
  isSubmitting: boolean;
}) {
  const [answers, setAnswers] = useState<Record<string, string>>({});

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    // Only submit questions that have answers
    const filled = Object.fromEntries(
      Object.entries(answers).filter(([, v]) => v.trim() !== ''),
    );
    if (Object.keys(filled).length > 0) {
      onSubmit(filled);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-3">
      {questions.map((q) => (
        <div key={q.id} className="flex flex-col gap-1">
          <label className="text-xs font-medium text-slate-700 leading-snug">
            {q.question}
          </label>
          <input
            type="text"
            value={answers[q.id] ?? ''}
            onChange={(e) =>
              setAnswers((prev) => ({ ...prev, [q.id]: e.target.value }))
            }
            placeholder="Your answer…"
            className="rounded-md border border-slate-300 px-2.5 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-indigo-400 focus:border-transparent"
          />
        </div>
      ))}
      <button
        type="submit"
        disabled={isSubmitting}
        className="mt-1 self-start rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50 transition-colors"
      >
        {isSubmitting ? 'Updating SOA…' : 'Fill in & regenerate'}
      </button>
    </form>
  );
}

// ---------------------------------------------------------------------------
// Main SOA Panel
// ---------------------------------------------------------------------------

export function SOAPanel() {
  const {
    isSOAPanelOpen,
    isSOAMaximized,
    soaSections,
    soaMissingQuestions,
    isSOAGenerating,
    closeSOAPanel,
    toggleSOAMaximize,
    submitSOAAnswers,
  } = useChatStore();

  const [showDownload, setShowDownload] = useState(false);
  const [isDownloading, setIsDownloading] = useState<'pdf' | 'word' | null>(null);
  const downloadRef = useRef<HTMLDivElement>(null);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (downloadRef.current && !downloadRef.current.contains(e.target as Node)) {
        setShowDownload(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const handleDownload = async (format: 'pdf' | 'word') => {
    setShowDownload(false);
    setIsDownloading(format);
    try {
      if (format === 'pdf') await downloadSOAasPDF(soaSections);
      else await downloadSOAasWord(soaSections);
    } finally {
      setIsDownloading(null);
    }
  };

  const hasMissing = soaMissingQuestions.length > 0;

  if (!isSOAPanelOpen) return null;

  return (
    <aside className="flex flex-col h-full w-full border-l border-slate-200 bg-slate-50 overflow-hidden">
      {/* ── Header ── */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-200 bg-white shrink-0">
        <div className="flex items-center gap-2">
          {/* Document icon */}
          <svg className="w-4 h-4 text-indigo-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
          <span className="text-sm font-semibold text-slate-800">Statement of Advice</span>
          {soaSections.length > 0 && (
            <span className="rounded-full bg-indigo-100 text-indigo-700 text-[10px] font-semibold px-2 py-0.5">
              {soaSections.length} section{soaSections.length !== 1 ? 's' : ''}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {/* Download dropdown */}
          {soaSections.length > 0 && (
            <div ref={downloadRef} className="relative">
              <button
                onClick={() => setShowDownload((v) => !v)}
                disabled={isDownloading !== null}
                className="flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium text-slate-600 border border-slate-200 hover:border-indigo-300 hover:text-indigo-600 hover:bg-indigo-50 transition-colors disabled:opacity-50"
              >
                {isDownloading ? (
                  <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                  </svg>
                ) : (
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                  </svg>
                )}
                {isDownloading === 'pdf' ? 'Exporting PDF…' : isDownloading === 'word' ? 'Exporting Word…' : 'Download'}
                {!isDownloading && (
                  <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                  </svg>
                )}
              </button>
              {showDownload && (
                <div className="absolute right-0 top-full mt-1 w-44 rounded-lg border border-slate-200 bg-white shadow-lg z-50 overflow-hidden">
                  <button
                    onClick={() => handleDownload('pdf')}
                    className="flex w-full items-center gap-2.5 px-3 py-2.5 text-xs text-slate-700 hover:bg-indigo-50 hover:text-indigo-700 transition-colors"
                  >
                    <svg className="w-4 h-4 text-red-500 shrink-0" fill="currentColor" viewBox="0 0 24 24">
                      <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8l-6-6zm-1 1.5L18.5 9H13V3.5zM9.3 15.5c-.1.3-.3.5-.6.7-.3.1-.6.2-1 .2H7v1.6H6v-4.5h1.7c.4 0 .7.1 1 .2.3.1.5.3.6.6.1.2.2.5.2.7 0 .3-.1.6-.2.8zm3.4.4c-.1.4-.3.7-.5.9-.2.2-.5.4-.8.5-.3.1-.7.1-1 .1H9.3v-4.5h1.1c.4 0 .7 0 1 .1.3.1.6.3.8.5.2.2.4.5.5.9.1.3.1.6.1 1s0 .7-.1 1zm3.3-2.6h-2v1.1h1.8v.8h-1.8v1.9H13v-4.5h3v.7z"/>
                    </svg>
                    Download as PDF
                  </button>
                  <div className="border-t border-slate-100" />
                  <button
                    onClick={() => handleDownload('word')}
                    className="flex w-full items-center gap-2.5 px-3 py-2.5 text-xs text-slate-700 hover:bg-indigo-50 hover:text-indigo-700 transition-colors"
                  >
                    <svg className="w-4 h-4 text-blue-600 shrink-0" fill="currentColor" viewBox="0 0 24 24">
                      <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8l-6-6zm-1 1.5L18.5 9H13V3.5zM7 15l1.5-4.5h1l1 3.2 1-3.2h1L14 15h-1l-1-3.1-1 3.1H7z"/>
                    </svg>
                    Download as Word
                  </button>
                </div>
              )}
            </div>
          )}

          {isSOAMaximized ? (
            <button
              onClick={toggleSOAMaximize}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium text-indigo-600 bg-indigo-50 hover:bg-indigo-100 transition-colors"
              title="Restore to side panel"
            >
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 9V4.5M9 9H4.5M9 9L3.75 3.75M15 9h4.5M15 9V4.5M15 9l5.25-5.25M15 15h4.5M15 15v4.5M15 15l5.25 5.25M9 15H4.5M9 15v4.5M9 15l-5.25 5.25" />
              </svg>
              Minimise
            </button>
          ) : (
            <button
              onClick={toggleSOAMaximize}
              className="text-slate-400 hover:text-slate-600 transition-colors p-1 rounded"
              title="Maximise panel"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 3.75v4.5m0-4.5h4.5m-4.5 0L9 9M3.75 20.25v-4.5m0 4.5h4.5m-4.5 0L9 15M20.25 3.75h-4.5m4.5 0v4.5m0-4.5L15 9m5.25 11.25h-4.5m4.5 0v-4.5m0 4.5L15 15" />
              </svg>
            </button>
          )}
          <button
            onClick={closeSOAPanel}
            className="text-slate-400 hover:text-slate-600 transition-colors p-1 rounded"
            title="Close SOA panel"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>

      {/* ── Missing fields banner ── */}
      {hasMissing && !isSOAGenerating && (
        <div className="shrink-0 border-b border-amber-200 bg-amber-50 px-4 py-3">
          <div className="flex items-start gap-2 mb-2">
            <svg className="w-4 h-4 text-amber-500 mt-0.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            <p className="text-xs font-semibold text-amber-800">
              {soaMissingQuestions.length} field{soaMissingQuestions.length !== 1 ? 's' : ''} need{soaMissingQuestions.length === 1 ? 's' : ''} your input
            </p>
          </div>
          <MissingFieldsForm
            questions={soaMissingQuestions}
            onSubmit={submitSOAAnswers}
            isSubmitting={isSOAGenerating}
          />
        </div>
      )}

      {/* ── Generating spinner ── */}
      {isSOAGenerating && (
        <div className="shrink-0 flex items-center gap-2 px-4 py-3 bg-indigo-50 border-b border-indigo-100">
          <svg className="w-4 h-4 text-indigo-500 animate-spin" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
          </svg>
          <span className="text-xs text-indigo-700 font-medium">Updating SOA…</span>
        </div>
      )}

      {/* ── TipTap editor ── */}
      <div className="flex-1 overflow-hidden p-3">
        <TipTapEditor sections={soaSections} />
      </div>
    </aside>
  );
}
