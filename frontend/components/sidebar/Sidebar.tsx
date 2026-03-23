'use client';

import { useState, useMemo } from 'react';
import { Plus, Search, Shield, X } from 'lucide-react';
import { useChatStore } from '@/store/chat-store';
import { ChatItem } from './ChatItem';
import { WorkspaceStatusCard } from './WorkspaceStatusCard';
import { cn } from '@/lib/utils';

export function Sidebar() {
  const {
    chats,
    activeChatId,
    searchQuery,
    setActiveChat,
    createNewChat,
    setSearchQuery,
    workspaceStatus,
    isLoadingChats,
  } = useChatStore();

  const filteredChats = useMemo(() => {
    if (!searchQuery.trim()) return chats;
    const q = searchQuery.toLowerCase();
    return chats.filter(
      (c) =>
        c.title.toLowerCase().includes(q) ||
        c.lastMessage.toLowerCase().includes(q)
    );
  }, [chats, searchQuery]);

  return (
    <aside className="flex h-full w-64 flex-col bg-slate-950 border-r border-slate-800/60">
      {/* Brand header */}
      <div className="flex items-center gap-3 px-4 pt-5 pb-4">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-indigo-600 shadow-lg shadow-indigo-900/40">
          <Shield size={16} className="text-white" />
        </div>
        <div className="min-w-0">
          <p className="text-sm font-semibold text-slate-100 leading-tight">Insurance AI</p>
          <p className="text-[10px] text-slate-500 leading-tight mt-0.5">Advisor Workspace</p>
        </div>
      </div>

      {/* New chat button */}
      <div className="px-3 pb-3">
        <button
          onClick={createNewChat}
          className="flex w-full items-center gap-2.5 rounded-xl border border-slate-700/80 bg-slate-900/60 px-3 py-2.5 text-sm text-slate-300 transition-all duration-150 hover:border-indigo-500/50 hover:bg-slate-800 hover:text-slate-100 active:scale-[0.98]"
        >
          <Plus size={15} className="text-indigo-400 shrink-0" />
          <span className="text-[13px] font-medium">New Chat</span>
        </button>
      </div>

      {/* Search */}
      <div className="px-3 pb-3">
        <div className="relative">
          <Search
            size={13}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-600 pointer-events-none"
          />
          <input
            type="text"
            placeholder="Search conversations…"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full rounded-lg bg-slate-900 border border-slate-800 py-2 pl-8 pr-8 text-[12px] text-slate-300 placeholder:text-slate-600 focus:outline-none focus:border-slate-600 focus:ring-1 focus:ring-slate-600/50 transition-colors"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-600 hover:text-slate-400 transition-colors"
            >
              <X size={11} />
            </button>
          )}
        </div>
      </div>

      {/* Section label */}
      <div className="px-4 pb-1.5">
        <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-600">
          Conversations
        </p>
      </div>

      {/* Chat list */}
      <div className="flex-1 overflow-y-auto px-2 pb-2 space-y-0.5 scrollbar-thin">
        {isLoadingChats ? (
          <div className="px-3 py-6 text-center">
            <p className="text-xs text-slate-600">Loading…</p>
          </div>
        ) : filteredChats.length === 0 ? (
          <div className="px-3 py-6 text-center">
            <p className="text-xs text-slate-600">No conversations found</p>
          </div>
        ) : (
          filteredChats.map((chat) => (
            <ChatItem
              key={chat.id}
              chat={chat}
              isActive={chat.id === activeChatId}
              onClick={() => setActiveChat(chat.id)}
            />
          ))
        )}
      </div>

      {/* Workspace status card */}
      <WorkspaceStatusCard status={workspaceStatus} />
    </aside>
  );
}
