'use client';

import { MessageSquare } from 'lucide-react';
import { cn, formatTimestamp } from '@/lib/utils';
import { Chat } from '@/lib/types';

interface ChatItemProps {
  chat: Chat;
  isActive: boolean;
  onClick: () => void;
}

export function ChatItem({ chat, isActive, onClick }: ChatItemProps) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'group w-full flex items-start gap-3 px-3 py-2.5 rounded-xl text-left transition-all duration-150 cursor-pointer',
        isActive
          ? 'bg-slate-800 text-slate-100'
          : 'text-slate-400 hover:bg-slate-800/60 hover:text-slate-200'
      )}
    >
      <MessageSquare
        className={cn(
          'mt-0.5 shrink-0 transition-colors',
          isActive
            ? 'text-indigo-400'
            : 'text-slate-600 group-hover:text-slate-400'
        )}
        size={14}
      />
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between gap-2">
          <p
            className={cn(
              'text-xs font-medium truncate',
              isActive ? 'text-slate-100' : 'text-slate-300'
            )}
          >
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
    </button>
  );
}
