'use client';

import { useRef } from 'react';
import { Upload, BookOpen, Menu, ChevronDown, FileText } from 'lucide-react';
import { useChatStore } from '@/store/chat-store';
import { Button } from '@/components/ui/button';

const ACCEPTED = '.pdf,.docx,.png,.jpg,.jpeg,.webp';
const MAX_SIZE = 20 * 1024 * 1024;

export function ChatHeader() {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { chats, activeChatId, messages, soaSections, toggleSidebar, isSOAGenerating, isSOAPanelOpen, closeSOAPanel, generateSOAForConversation, isSourcesPanelOpen, openSourcesPanel, closeSourcesPanel, uploadAndAddFile } = useChatStore();

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files) return;
    Array.from(files).forEach((file) => {
      if (file.size <= MAX_SIZE) uploadAndAddFile(file);
    });
    e.target.value = '';
  };

  const handleGenerateSOA = () => {
    if (isSOAPanelOpen) {
      closeSOAPanel();
    } else {
      generateSOAForConversation();
    }
  };
  const activeChat = chats.find((c) => c.id === activeChatId);

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-slate-200 bg-white px-4 shadow-sm shadow-slate-100/80">
      {/* Left: toggle + title */}
      <div className="flex items-center gap-3 min-w-0">
        <button
          onClick={toggleSidebar}
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100 hover:text-slate-600 transition-colors"
          aria-label="Toggle sidebar"
        >
          <Menu size={16} />
        </button>
        <div className="min-w-0">
          <h1 className="text-sm font-semibold text-slate-800 truncate">
            {activeChat?.title ?? 'New Conversation'}
          </h1>
          {activeChat && (
            <p className="text-[11px] text-slate-400 mt-0.5">
              {messages.length} {messages.length === 1 ? 'message' : 'messages'}
            </p>
          )}
        </div>
      </div>

      {/* Right: actions */}
      <div className="flex items-center gap-2 shrink-0">
        <Button
          variant="outline"
          size="sm"
          onClick={() => fileInputRef.current?.click()}
          className="hidden sm:flex gap-1.5 text-slate-600 border-slate-200 hover:border-indigo-300 hover:text-indigo-600 hover:bg-indigo-50"
        >
          <Upload size={13} />
          <span>Upload File</span>
        </Button>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept={ACCEPTED}
          className="hidden"
          onChange={handleFileChange}
        />
        <Button
          variant={isSourcesPanelOpen ? 'default' : 'outline'}
          size="sm"
          onClick={() => isSourcesPanelOpen ? closeSourcesPanel() : openSourcesPanel()}
          className={
            isSourcesPanelOpen
              ? 'hidden sm:flex gap-1.5 bg-indigo-600 hover:bg-indigo-700 text-white'
              : 'hidden sm:flex gap-1.5 text-slate-600 border-slate-200 hover:border-indigo-300 hover:text-indigo-600 hover:bg-indigo-50'
          }
        >
          <BookOpen size={13} />
          <span>Sources</span>
        </Button>
        {activeChatId && (
          <Button
            variant={isSOAPanelOpen ? 'default' : 'outline'}
            size="sm"
            onClick={handleGenerateSOA}
            disabled={isSOAGenerating}
            className={
              isSOAPanelOpen
                ? 'hidden sm:flex gap-1.5 bg-indigo-600 hover:bg-indigo-700 text-white'
                : 'hidden sm:flex gap-1.5 text-slate-600 border-slate-200 hover:border-indigo-300 hover:text-indigo-600 hover:bg-indigo-50'
            }
          >
            <FileText size={13} />
            <span>{isSOAGenerating ? 'Generating…' : isSOAPanelOpen ? 'Close SOA' : soaSections.length > 0 ? 'View SOA' : 'Generate SOA'}</span>
          </Button>
        )}
        {/* Mobile compact */}
        <button className="flex sm:hidden h-8 w-8 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100 transition-colors">
          <ChevronDown size={16} />
        </button>
      </div>
    </header>
  );
}
