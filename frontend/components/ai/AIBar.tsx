'use client';

import { useRef, useEffect, KeyboardEvent, useState } from 'react';
import {
  Send, Paperclip, X, Loader2, ChevronDown, User, Sparkles,
  CheckCircle2, AlertCircle,
} from 'lucide-react';
import { useOrchestratorStore } from '../../store/orchestrator-store';
import { useClientStore } from '../../store/client-store';
import AgentWorkspacePanel from './AgentWorkspacePanel';
import { uploadFile, USER_ID } from '../../lib/api';
import { generateId } from '../../lib/utils';
import type { PageContext } from '../../lib/types';

// ---------------------------------------------------------------------------
// Slash command definitions
// ---------------------------------------------------------------------------

const SLASH_COMMANDS = [
  { command: '/analyze-life-insurance', label: 'Analyse Life Insurance in Super', description: 'Run life insurance in superannuation analysis' },
  { command: '/analyze-tpd', label: 'Analyse TPD Policy', description: 'Run TPD policy assessment' },
  { command: '/analyze-ip', label: 'Analyse Income Protection', description: 'Run income protection policy analysis' },
  { command: '/analyze-tpd-super', label: 'Analyse TPD in Super', description: 'Run TPD in superannuation analysis' },
  { command: '/analyze-ip-super', label: 'Analyse IP in Super', description: 'Run income protection in super analysis' },
  { command: '/analyze-trauma', label: 'Analyse Trauma / CI', description: 'Run trauma / critical illness analysis' },
  { command: '/analyze-life-tpd', label: 'Analyse Life + TPD', description: 'Run combined life and TPD policy analysis' },
  { command: '/generate-soa', label: 'Generate Statement of Advice', description: 'Generate SOA document for this client' },
  { command: '/check-factfind', label: 'Check Fact Find', description: "Show client's fact find data" },
  { command: '/check-insurance', label: 'Check Insurance Details', description: "Show client's existing insurance" },
  { command: '/check-goals', label: 'Check Goals & Risk Profile', description: "Show client's goals and risk profile" },
];

const COMMAND_EXPANSIONS: Record<string, string> = {
  '/analyze-life-insurance': 'Analyse life insurance in super for this client',
  '/analyze-tpd':            'Analyse TPD policy for this client',
  '/analyze-ip':             'Analyse income protection policy for this client',
  '/analyze-tpd-super':      'Analyse TPD in superannuation for this client',
  '/analyze-ip-super':       'Analyse income protection in super for this client',
  '/analyze-trauma':         'Analyse trauma and critical illness policy for this client',
  '/analyze-life-tpd':       'Analyse life and TPD combined policy for this client',
  '/generate-soa':           'Generate a Statement of Advice for this client',
  '/check-factfind':         "Show me the fact find for this client",
  '/check-insurance':        "What insurance does this client have?",
  '/check-goals':            "What are this client's goals and risk profile?",
};

export default function AIBar() {
  const {
    phase, inputValue, setInput,
    pendingFiles, addFile, removeFile, updateFile,
    currentPlan, stepResults, synthesizedResponse,
    clarificationQuestion, clarificationOptions,
    missingFieldMode, currentMissingField,
    error, isWorkspaceOpen,
    submitInstruction, confirmPlan, cancelPlan, answerClarification,
    openWorkspace, closeWorkspace, reset,
  } = useOrchestratorStore();

  const {
    activeClientId,
    activeClientName,
    activeWorkspace,
    currentView,
    loadDocuments,
  } = useClientStore();

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [slashOpen, setSlashOpen] = useState(false);
  const [slashFilter, setSlashFilter] = useState('');
  const [clarificationInput, setClarificationInput] = useState('');

  const isRunning = phase === 'planning' || phase === 'executing';
  const isConfirming = phase === 'confirming';
  const isClarifying = phase === 'clarifying';
  const isComplete = phase === 'complete';
  const isError = phase === 'error';

  const hasContent = inputValue.trim() || pendingFiles.some((f) => f.storage_ref);
  const canSubmit = hasContent && !isRunning && !isConfirming && !isClarifying
    && !pendingFiles.some((f) => f.uploading) && !!activeClientId;

  // Auto-resize textarea
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 140) + 'px';
  }, [inputValue]);

  // Open workspace when a run starts
  useEffect(() => {
    if (isRunning || isConfirming || isClarifying) openWorkspace();
  }, [phase]);

  // Detect slash command in input
  const handleInputChange = (value: string) => {
    setInput(value);
    if (value.startsWith('/') && !value.includes(' ')) {
      setSlashOpen(true);
      setSlashFilter(value.slice(1).toLowerCase());
    } else {
      setSlashOpen(false);
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (slashOpen) {
        const filtered = getFilteredCommands();
        if (filtered.length > 0) selectSlashCommand(filtered[0].command);
      } else {
        handleSubmit();
      }
    }
    if (e.key === 'Escape') setSlashOpen(false);
  };

  const selectSlashCommand = (command: string) => {
    setInput(COMMAND_EXPANSIONS[command] ?? command);
    setSlashOpen(false);
    textareaRef.current?.focus();
  };

  const getFilteredCommands = () =>
    SLASH_COMMANDS.filter((c) =>
      c.command.slice(1).includes(slashFilter) ||
      c.label.toLowerCase().includes(slashFilter)
    );

  const buildPageContext = (): PageContext => ({
    currentPage: typeof window !== 'undefined' ? window.location.pathname : '/',
    selectedClientId: activeClientId ?? undefined,
    selectedClientName: activeClientName ?? undefined,
  });

  const handleSubmit = async () => {
    if (!canSubmit || !activeClientId) return;
    const instruction = inputValue.trim();
    if (!instruction) return;
    await submitInstruction(instruction, buildPageContext(), pendingFiles);
  };

  const handleFileSelect = async (files: FileList | null) => {
    if (!files) return;
    for (const file of Array.from(files)) {
      const id = generateId();
      addFile({ id, name: file.name, type: file.type, size: file.size, uploading: true });
      try {
        const conversationId = activeWorkspace?.active_conversation_id ?? null;
        const res = await uploadFile(file, USER_ID, conversationId, activeClientId ?? null);
        updateFile(id, { uploading: false, storage_ref: res.storage_ref, facts_summary: res.facts_summary });
        if (activeClientId) void loadDocuments(activeClientId);
      } catch (err) {
        updateFile(id, { uploading: false, upload_error: err instanceof Error ? err.message : 'Upload failed' });
      }
    }
  };

  const handleClarificationSubmit = () => {
    const answer = clarificationInput.trim();
    if (!answer) return;
    setClarificationInput('');
    answerClarification(answer);
  };

  const contextLabel = currentView === 'profile' && activeClientName ? activeClientName : 'No client selected';
  const isContextActive = currentView === 'profile' && !!activeClientId;

  // Phase label for header
  const phaseLabel = {
    idle: '',
    planning: 'Planning…',
    confirming: 'Review plan',
    executing: 'Executing…',
    complete: 'Done',
    error: 'Error',
    clarifying: 'Clarification needed',
  }[phase] ?? '';

  return (
    <div className="flex-shrink-0 bg-white border-t border-slate-200 shadow-sm">

      {/* Workspace panel (expands above input) */}
      {isWorkspaceOpen && (isRunning || isConfirming || isClarifying || isComplete || isError) && (
        <AgentWorkspacePanel
          phase={phase}
          plan={currentPlan}
          stepResults={stepResults}
          synthesizedResponse={synthesizedResponse}
          clarificationQuestion={clarificationQuestion}
          clarificationOptions={clarificationOptions}
          error={error}
          onConfirm={confirmPlan}
          onCancel={cancelPlan}
          onAnswerClarification={answerClarification}
          onClose={() => {
            closeWorkspace();
            if (phase === 'complete' || phase === 'error') reset();
          }}
        />
      )}

      {/* File chips */}
      {pendingFiles.length > 0 && (
        <div className="px-4 pt-2 flex gap-2 flex-wrap">
          {pendingFiles.map((f) => (
            <div
              key={f.id}
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs border ${
                f.upload_error
                  ? 'bg-red-50 border-red-200 text-red-600'
                  : f.uploading
                  ? 'bg-indigo-50 border-indigo-200 text-indigo-600'
                  : 'bg-slate-50 border-slate-200 text-slate-600'
              }`}
            >
              {f.uploading && <Loader2 size={10} className="animate-spin" />}
              <span className="max-w-[140px] truncate">{f.name}</span>
              <button onClick={() => removeFile(f.id)} className="hover:text-slate-800">
                <X size={10} />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Clarification inline input (shown instead of normal input when clarifying) */}
      {isClarifying && clarificationQuestion && (
        <div className={`px-4 py-3 border-b ${missingFieldMode ? 'bg-blue-50 border-blue-100' : 'bg-amber-50 border-amber-100'}`}>
          <div className="flex items-start gap-2 mb-2">
            <AlertCircle size={14} className={`flex-shrink-0 mt-0.5 ${missingFieldMode ? 'text-blue-500' : 'text-amber-500'}`} />
            <div>
              <p className={`text-sm font-medium ${missingFieldMode ? 'text-blue-900' : 'text-amber-800'}`}>{clarificationQuestion}</p>
              {missingFieldMode && (
                <p className="text-xs text-blue-500 mt-0.5">This value is needed to run the analysis</p>
              )}
            </div>
          </div>
          {clarificationOptions.length > 0 && (
            <div className="flex gap-2 flex-wrap mb-2">
              {clarificationOptions.map((opt) => (
                <button
                  key={opt}
                  onClick={() => answerClarification(opt)}
                  className="px-3 py-1 text-xs bg-white border border-amber-200 text-amber-700 rounded-full hover:bg-amber-50 transition-colors"
                >
                  {opt}
                </button>
              ))}
            </div>
          )}
          <div className="flex gap-2">
            <input
              type={missingFieldMode && currentMissingField?.input_type === 'number' ? 'number' : 'text'}
              value={clarificationInput}
              onChange={(e) => setClarificationInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleClarificationSubmit()}
              placeholder={missingFieldMode ? `Enter ${currentMissingField?.label ?? 'value'}…` : 'Type your answer…'}
              min={missingFieldMode && currentMissingField?.input_type === 'number' ? 0 : undefined}
              className={`flex-1 text-sm rounded-lg px-3 py-1.5 focus:outline-none focus:ring-2 bg-white border ${
                missingFieldMode
                  ? 'border-blue-200 focus:ring-blue-300'
                  : 'border-amber-200 focus:ring-amber-300'
              }`}
              autoFocus
            />
            <button
              onClick={handleClarificationSubmit}
              disabled={!clarificationInput.trim()}
              className={`px-3 py-1.5 text-white text-sm rounded-lg disabled:opacity-40 transition-colors ${
                missingFieldMode ? 'bg-blue-500 hover:bg-blue-600' : 'bg-amber-500 hover:bg-amber-600'
              }`}
            >
              {missingFieldMode ? 'Provide' : 'Answer'}
            </button>
          </div>
        </div>
      )}

      {/* Slash command dropdown */}
      {slashOpen && (
        <div className="px-4 pb-1">
          <div className="bg-white border border-slate-200 rounded-lg shadow-lg overflow-hidden">
            {getFilteredCommands().slice(0, 8).map((cmd) => (
              <button
                key={cmd.command}
                onClick={() => selectSlashCommand(cmd.command)}
                className="w-full text-left px-3 py-2 hover:bg-indigo-50 transition-colors flex items-baseline gap-2 text-sm"
              >
                <span className="font-mono text-indigo-600 text-xs">{cmd.command}</span>
                <span className="text-slate-700 font-medium text-xs">{cmd.label}</span>
                <span className="text-slate-400 text-xs hidden sm:block">{cmd.description}</span>
              </button>
            ))}
            {getFilteredCommands().length === 0 && (
              <p className="px-3 py-2 text-xs text-slate-400">No matching commands</p>
            )}
          </div>
        </div>
      )}

      {/* Main input row */}
      <div className="flex items-end gap-2 px-4 py-3">
        {/* Sparkles + context badge */}
        <div className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium flex-shrink-0 mb-0.5 ${
          isContextActive
            ? 'bg-indigo-50 text-indigo-700 border border-indigo-200'
            : 'bg-slate-100 text-slate-400 border border-slate-200'
        }`}>
          <Sparkles size={11} />
          <span className="max-w-[120px] truncate">{contextLabel}</span>
        </div>

        {/* Phase status when running/confirming */}
        {phaseLabel && phase !== 'idle' && (
          <div className={`flex items-center gap-1 px-2 py-1 rounded text-xs font-medium flex-shrink-0 mb-0.5 ${
            isRunning ? 'text-indigo-500' :
            isComplete ? 'text-emerald-600' :
            isError ? 'text-red-500' :
            'text-amber-600'
          }`}>
            {isRunning && <Loader2 size={11} className="animate-spin" />}
            {isComplete && <CheckCircle2 size={11} />}
            {isError && <AlertCircle size={11} />}
            <span>{phaseLabel}</span>
          </div>
        )}

        {/* Textarea — hidden during clarification */}
        {!isClarifying && (
          <textarea
            ref={textareaRef}
            value={inputValue}
            onChange={(e) => handleInputChange(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isRunning || isConfirming}
            placeholder={
              isRunning
                ? 'Processing…'
                : isConfirming
                ? 'Waiting for your confirmation above…'
                : isContextActive
                ? `Ask about ${activeClientName}… (type / for commands)`
                : 'Select a client, then ask a question…'
            }
            rows={1}
            className="flex-1 resize-none text-sm text-slate-900 placeholder-slate-400 bg-transparent focus:outline-none leading-relaxed py-1.5 disabled:opacity-50"
          />
        )}

        {/* Spacer when clarifying */}
        {isClarifying && <div className="flex-1" />}

        {/* Upload button */}
        {!isConfirming && !isClarifying && (
          <>
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={isRunning}
              className="p-2 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-lg transition-colors flex-shrink-0 mb-0.5 disabled:opacity-40"
            >
              <Paperclip size={16} />
            </button>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept=".pdf,.docx,.png,.jpg,.jpeg,.webp"
              className="hidden"
              onChange={(e) => handleFileSelect(e.target.files)}
            />
          </>
        )}

        {/* Collapse/expand workspace if result exists */}
        {(isComplete || isError) && !isWorkspaceOpen && (
          <button
            onClick={openWorkspace}
            className="p-2 text-indigo-500 hover:text-indigo-700 hover:bg-indigo-50 rounded-lg transition-colors flex-shrink-0 mb-0.5"
          >
            <ChevronDown size={16} className="rotate-180" />
          </button>
        )}

        {/* Send button — hidden during confirm/clarify */}
        {!isConfirming && !isClarifying && (
          <button
            onClick={handleSubmit}
            disabled={!canSubmit}
            className={`p-2 rounded-lg transition-colors flex-shrink-0 mb-0.5 ${
              canSubmit
                ? 'bg-indigo-600 text-white hover:bg-indigo-700'
                : 'bg-slate-100 text-slate-300 cursor-not-allowed'
            }`}
          >
            {isRunning ? (
              <Loader2 size={16} className="animate-spin" />
            ) : (
              <Send size={16} />
            )}
          </button>
        )}
      </div>
    </div>
  );
}
