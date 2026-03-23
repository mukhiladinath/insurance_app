'use client';

import { Upload, BookOpen, Menu, ChevronDown } from 'lucide-react';
import { useChatStore } from '@/store/chat-store';
import { Button } from '@/components/ui/button';

interface ChatHeaderProps {
  onUploadClick?: () => void;
  onViewSourcesClick?: () => void;
}

export function ChatHeader({ onUploadClick, onViewSourcesClick }: ChatHeaderProps) {
  const { chats, activeChatId, toggleSidebar } = useChatStore();
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
              {activeChat.messageCount} messages
            </p>
          )}
        </div>
      </div>

      {/* Right: actions */}
      <div className="flex items-center gap-2 shrink-0">
        <Button
          variant="outline"
          size="sm"
          onClick={onUploadClick}
          className="hidden sm:flex gap-1.5 text-slate-600 border-slate-200 hover:border-indigo-300 hover:text-indigo-600 hover:bg-indigo-50"
        >
          <Upload size={13} />
          <span>Upload File</span>
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={onViewSourcesClick}
          className="hidden sm:flex gap-1.5 text-slate-600 border-slate-200 hover:border-indigo-300 hover:text-indigo-600 hover:bg-indigo-50"
        >
          <BookOpen size={13} />
          <span>View Sources</span>
        </Button>
        {/* Mobile compact */}
        <button className="flex sm:hidden h-8 w-8 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100 transition-colors">
          <ChevronDown size={16} />
        </button>
      </div>
    </header>
  );
}
