'use client';

import { useEffect } from 'react';
import { useChatStore } from '@/store/chat-store';
import { Sidebar } from './sidebar/Sidebar';
import { ChatHeader } from './chat/ChatHeader';
import { MessageList } from './chat/MessageList';
import { PromptComposer } from './chat/PromptComposer';
import { cn } from '@/lib/utils';

export function ChatLayout() {
  const { isSidebarOpen, loadConversations, refreshWorkspaceStatus } = useChatStore();

  useEffect(() => {
    loadConversations();
    refreshWorkspaceStatus();

    // Poll workspace status every 30 seconds
    const interval = setInterval(refreshWorkspaceStatus, 30_000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-white">
      {/* ── Sidebar ── */}
      <div
        className={cn(
          'transition-all duration-300 ease-in-out shrink-0 overflow-hidden',
          isSidebarOpen ? 'w-64' : 'w-0'
        )}
      >
        <Sidebar />
      </div>

      {/* ── Main area ── */}
      <main className="flex flex-1 flex-col overflow-hidden min-w-0">
        {/* Top header bar */}
        <ChatHeader />

        {/* Message area — scrollable */}
        <MessageList />

        {/* Prompt composer — sticky bottom */}
        <PromptComposer />
      </main>
    </div>
  );
}
