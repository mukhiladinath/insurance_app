'use client';

import { useState } from 'react';
import { MessageSquare, Trash2 } from 'lucide-react';
import { cn, formatTimestamp } from '@/lib/utils';
import { useChatStore } from '@/store/chat-store';
import { ConfirmModal } from '@/components/ui/ConfirmModal';
import { Chat } from '@/lib/types';

interface ChatItemProps {
  chat: Chat;
  isActive: boolean;
  onClick: () => void;
}

export function ChatItem({ chat, isActive, onClick }: ChatItemProps) {
  const { deleteChat } = useChatStore();
  const [showConfirm, setShowConfirm] = useState(false);

  const handleDeleteClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    setShowConfirm(true);
  };

  return (
    <>
      <div
        className={cn(
          'group relative w-full flex items-start gap-3 px-3 py-2.5 rounded-xl text-left transition-all duration-150 cursor-pointer',
          isActive
            ? 'bg-slate-800 text-slate-100'
            : 'text-slate-400 hover:bg-slate-800/60 hover:text-slate-200'
        )}
        onClick={onClick}
      >
        <MessageSquare
          className={cn(
            'mt-0.5 shrink-0 transition-colors',
            isActive ? 'text-indigo-400' : 'text-slate-600 group-hover:text-slate-400'
          )}
          size={14}
        />
        <div className="flex-1 min-w-0 pr-5">
          <div className="flex items-center justify-between gap-2">
            <p className={cn('text-xs font-medium truncate', isActive ? 'text-slate-100' : 'text-slate-300')}>
              {chat.title}
            </p>
            <span className="text-[10px] text-slate-600 shrink-0" suppressHydrationWarning>
              {formatTimestamp(chat.timestamp)}
            </span>
          </div>
          <p className="text-[11px] text-slate-500 truncate mt-0.5 leading-relaxed">
            {chat.lastMessage}
          </p>
        </div>

        <button
          onClick={handleDeleteClick}
          title="Delete conversation"
          className="absolute right-2 top-1/2 -translate-y-1/2 flex items-center justify-center w-6 h-6 rounded-md opacity-0 group-hover:opacity-100 text-slate-500 hover:text-red-400 hover:bg-red-400/10 transition-all"
        >
          <Trash2 size={12} />
        </button>
      </div>

      {showConfirm && (
        <ConfirmModal
          title="Delete conversation?"
          message={`"${chat.title}" and all its messages will be permanently deleted.`}
          confirmLabel="Delete"
          cancelLabel="Cancel"
          onConfirm={() => { setShowConfirm(false); deleteChat(chat.id); }}
          onCancel={() => setShowConfirm(false)}
        />
      )}
    </>
  );
}
