'use client';

import { useRef, useState, useCallback, DragEvent, ChangeEvent, KeyboardEvent } from 'react';
import { Paperclip, Send, X, FileText } from 'lucide-react';
import { useChatStore } from '@/store/chat-store';
import { generateId, formatFileSize, cn } from '@/lib/utils';
import { Attachment } from '@/lib/types';
import { UploadHint } from './UploadHint';

const ACCEPTED_TYPES = ['application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'image/png', 'image/jpeg', 'image/jpg', 'image/webp'];
const MAX_FILE_SIZE = 20 * 1024 * 1024; // 20MB

export function PromptComposer() {
  const [value, setValue] = useState('');
  const [isDragging, setIsDragging] = useState(false);
  const [showUploadHint, setShowUploadHint] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const { sendMessage, pendingFiles, addPendingFile, removePendingFile, isStreaming } =
    useChatStore();

  const handleFiles = useCallback(
    (files: FileList | null) => {
      if (!files) return;
      Array.from(files).forEach((file) => {
        if (file.size > MAX_FILE_SIZE) return;
        const attachment: Attachment = {
          id: generateId(),
          name: file.name,
          type: file.type,
          size: file.size,
        };
        addPendingFile(attachment);
      });
    },
    [addPendingFile]
  );

  const handleSend = useCallback(() => {
    const trimmed = value.trim();
    if (!trimmed && pendingFiles.length === 0) return;
    if (isStreaming) return;

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
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleTextareaChange = (e: ChangeEvent<HTMLTextAreaElement>) => {
    setValue(e.target.value);
    // Auto-grow
    const el = e.target;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 180)}px`;
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

  const canSend = (value.trim().length > 0 || pendingFiles.length > 0) && !isStreaming;

  return (
    <div
      className="border-t border-slate-200 bg-white px-4 pt-3 pb-4 shadow-[0_-4px_20px_-4px_rgba(0,0,0,0.06)]"
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      <div className="mx-auto max-w-3xl space-y-2">
        {/* Upload hint — shown on drag or toggle */}
        {(showUploadHint || isDragging) && (
          <UploadHint isDragging={isDragging} />
        )}

        {/* File chips */}
        {pendingFiles.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {pendingFiles.map((file) => (
              <div
                key={file.id}
                className="flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs"
              >
                <FileText size={12} className="text-indigo-500 shrink-0" />
                <span className="max-w-[140px] truncate text-slate-700 font-medium">
                  {file.name}
                </span>
                <span className="text-slate-400">{formatFileSize(file.size)}</span>
                <button
                  onClick={() => removePendingFile(file.id)}
                  className="ml-0.5 text-slate-400 hover:text-red-500 transition-colors"
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
