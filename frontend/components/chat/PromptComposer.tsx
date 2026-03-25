'use client';

import { useRef, useState, useCallback, DragEvent, ChangeEvent, KeyboardEvent } from 'react';
import { Paperclip, Send, X, FileText, Loader2, AlertCircle, CheckCircle2 } from 'lucide-react';
import { useChatStore } from '@/store/chat-store';
import { formatFileSize, cn } from '@/lib/utils';
import { UploadHint } from './UploadHint';
import { SlashMenu, SlashCommand, SLASH_COMMANDS } from './SlashMenu';

const ACCEPTED_TYPES = ['application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'image/png', 'image/jpeg', 'image/jpg', 'image/webp'];
const MAX_FILE_SIZE = 20 * 1024 * 1024; // 20MB

export function PromptComposer() {
  const [value, setValue] = useState('');
  const [isDragging, setIsDragging] = useState(false);
  const [showUploadHint, setShowUploadHint] = useState(false);
  const [showSlashMenu, setShowSlashMenu] = useState(false);
  const [slashQuery, setSlashQuery] = useState('');
  const [slashActiveIndex, setSlashActiveIndex] = useState(0);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const { sendMessage, pendingFiles, uploadAndAddFile, removePendingFile, isStreaming } =
    useChatStore();

  const handleFiles = useCallback(
    (files: FileList | null) => {
      if (!files) return;
      Array.from(files).forEach((file) => {
        if (file.size > MAX_FILE_SIZE) return;
        // Upload immediately — uploadAndAddFile handles adding to pendingFiles
        uploadAndAddFile(file);
      });
    },
    [uploadAndAddFile]
  );

  // Slash command filtering (mirrors SlashMenu logic so Enter key works)
  const filteredSlashCommands = SLASH_COMMANDS.filter(
    (c) =>
      slashQuery === '' ||
      c.label.toLowerCase().includes(slashQuery.toLowerCase()) ||
      c.description.toLowerCase().includes(slashQuery.toLowerCase()),
  );

  const handleSlashSelect = useCallback(
    (cmd: SlashCommand) => {
      // Replace the /query portion at end of input with the command prompt
      const newValue = value.replace(/(^|\s)\/\S*$/, (match, prefix) => prefix + cmd.prompt);
      setValue(newValue);
      setShowSlashMenu(false);
      setTimeout(() => {
        if (textareaRef.current) {
          textareaRef.current.focus();
          textareaRef.current.setSelectionRange(newValue.length, newValue.length);
          textareaRef.current.style.height = 'auto';
          textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 180)}px`;
        }
      }, 0);
    },
    [value],
  );

  // Prevent sending while any file is still uploading
  const anyUploading = pendingFiles.some((f) => f.uploading);

  const handleSend = useCallback(() => {
    const trimmed = value.trim();
    if (!trimmed && pendingFiles.length === 0) return;
    if (isStreaming || anyUploading) return;

    sendMessage(
      trimmed || '(Attached files)',
      pendingFiles.length > 0 ? [...pendingFiles] : undefined,
    );

    setValue('');
    setShowUploadHint(false);

    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  }, [value, pendingFiles, isStreaming, sendMessage]);

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (showSlashMenu) {
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        setSlashActiveIndex((i) => Math.max(0, i - 1));
        return;
      }
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setSlashActiveIndex((i) => Math.min(i + 1, filteredSlashCommands.length - 1));
        return;
      }
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        const cmd = filteredSlashCommands[slashActiveIndex];
        if (cmd) handleSlashSelect(cmd);
        return;
      }
      if (e.key === 'Escape') {
        e.preventDefault();
        setShowSlashMenu(false);
        return;
      }
    }
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleTextareaChange = (e: ChangeEvent<HTMLTextAreaElement>) => {
    const text = e.target.value;
    setValue(text);
    // Auto-grow
    const el = e.target;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 180)}px`;
    // Slash menu: detect /query at end of input (start of line or after whitespace)
    const slashMatch = text.match(/(^|\s)\/(\S*)$/);
    if (slashMatch) {
      setSlashQuery(slashMatch[2]);
      setShowSlashMenu(true);
      setSlashActiveIndex(0);
    } else {
      setShowSlashMenu(false);
    }
  };

  const handleDragOver = (e: DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e: DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    handleFiles(e.dataTransfer.files);
  };

  const canSend = (value.trim().length > 0 || pendingFiles.length > 0) && !isStreaming && !anyUploading;

  return (
    <div
      className="border-t border-slate-200 bg-white px-4 pt-3 pb-4 shadow-[0_-4px_20px_-4px_rgba(0,0,0,0.06)]"
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      <div className="relative mx-auto max-w-3xl space-y-2">
        {/* Slash command menu — appears above the composer */}
        {showSlashMenu && (
          <SlashMenu
            query={slashQuery}
            onSelect={handleSlashSelect}
            onClose={() => setShowSlashMenu(false)}
            activeIndex={slashActiveIndex}
            setActiveIndex={setSlashActiveIndex}
          />
        )}

        {/* Upload hint — shown on drag or toggle */}
        {(showUploadHint || isDragging) && (
          <UploadHint isDragging={isDragging} />
        )}

        {/* File chips */}
        {pendingFiles.length > 0 && (
          <div className="flex flex-col gap-1.5">
            {pendingFiles.map((file) => (
              <div
                key={file.id}
                className={cn(
                  'flex items-start gap-2 rounded-xl border px-3 py-1.5 text-xs',
                  file.upload_error
                    ? 'border-red-200 bg-red-50'
                    : file.uploading
                    ? 'border-indigo-200 bg-indigo-50'
                    : 'border-slate-200 bg-slate-50'
                )}
              >
                {/* Status icon */}
                <div className="mt-0.5 shrink-0">
                  {file.uploading ? (
                    <Loader2 size={12} className="text-indigo-500 animate-spin" />
                  ) : file.upload_error ? (
                    <AlertCircle size={12} className="text-red-500" />
                  ) : file.storage_ref ? (
                    <CheckCircle2 size={12} className="text-emerald-500" />
                  ) : (
                    <FileText size={12} className="text-indigo-500" />
                  )}
                </div>

                {/* File info */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span className="max-w-[160px] truncate text-slate-700 font-medium">
                      {file.name}
                    </span>
                    <span className="text-slate-400 shrink-0">{formatFileSize(file.size)}</span>
                  </div>
                  {file.uploading && (
                    <p className="text-indigo-500 mt-0.5">Extracting text and client details…</p>
                  )}
                  {file.upload_error && (
                    <p className="text-red-500 mt-0.5">{file.upload_error}</p>
                  )}
                  {file.facts_summary && !file.uploading && !file.upload_error && (
                    <p className="text-emerald-700 mt-0.5 line-clamp-2">{file.facts_summary}</p>
                  )}
                  {file.storage_ref && !file.facts_summary && !file.uploading && (
                    <p className="text-slate-400 mt-0.5">Ready — no client details detected</p>
                  )}
                </div>

                {/* Remove button */}
                <button
                  onClick={() => removePendingFile(file.id)}
                  className="shrink-0 text-slate-400 hover:text-red-500 transition-colors mt-0.5"
                >
                  <X size={11} />
                </button>
              </div>
            ))}
          </div>
        )}

        {/* Main composer box */}
        <div
          className={cn(
            'flex items-end gap-2 rounded-2xl border bg-white px-3 py-2.5 transition-all duration-150',
            isDragging
              ? 'border-indigo-400 shadow-md shadow-indigo-100'
              : 'border-slate-200 shadow-sm hover:border-slate-300 focus-within:border-indigo-400 focus-within:shadow-md focus-within:shadow-indigo-100/60'
          )}
        >
          {/* Attach button */}
          <button
            onClick={() => {
              setShowUploadHint((v) => !v);
              fileInputRef.current?.click();
            }}
            className={cn(
              'flex h-8 w-8 shrink-0 items-center justify-center rounded-lg transition-all duration-150',
              showUploadHint
                ? 'bg-indigo-100 text-indigo-600'
                : 'text-slate-400 hover:bg-slate-100 hover:text-slate-600'
            )}
            title="Attach file"
          >
            <Paperclip size={16} />
          </button>

          {/* Hidden file input */}
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept=".pdf,.docx,.png,.jpg,.jpeg,.webp"
            className="hidden"
            onChange={(e) => handleFiles(e.target.files)}
          />

          {/* Textarea */}
          <textarea
            ref={textareaRef}
            value={value}
            onChange={handleTextareaChange}
            onKeyDown={handleKeyDown}
            placeholder="Ask about a policy, upload a document, or request an analysis…"
            rows={1}
            disabled={isStreaming}
            className="flex-1 resize-none bg-transparent text-sm text-slate-800 placeholder:text-slate-400 focus:outline-none disabled:opacity-60 leading-relaxed py-0.5 max-h-[180px] overflow-y-auto"
          />

          {/* Send button */}
          <button
            onClick={handleSend}
            disabled={!canSend}
            className={cn(
              'flex h-8 w-8 shrink-0 items-center justify-center rounded-lg transition-all duration-150',
              canSend
                ? 'bg-indigo-600 text-white hover:bg-indigo-700 active:scale-95 shadow-sm shadow-indigo-300'
                : 'bg-slate-100 text-slate-400 cursor-not-allowed'
            )}
            title="Send message"
          >
            <Send size={14} />
          </button>
        </div>

        {/* Footer hint */}
        <p className="text-center text-[10px] text-slate-400">
          Press <kbd className="rounded bg-slate-100 px-1 py-0.5 font-mono text-[9px] text-slate-500">Enter</kbd> to send
          {' · '}
          <kbd className="rounded bg-slate-100 px-1 py-0.5 font-mono text-[9px] text-slate-500">Shift+Enter</kbd> for new line
          {' · '}
          PDF, DOCX, images supported
        </p>
      </div>
    </div>
  );
}
