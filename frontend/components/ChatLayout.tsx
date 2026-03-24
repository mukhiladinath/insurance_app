'use client';

import { useEffect } from 'react';
import { useChatStore } from '@/store/chat-store';
import { Sidebar } from './sidebar/Sidebar';
import { ChatHeader } from './chat/ChatHeader';
import { MessageList } from './chat/MessageList';
import { PromptComposer } from './chat/PromptComposer';
import { SOAPanel } from './soa/SOAPanel';
import { SourcesPanel } from './sources/SourcesPanel';
import { cn } from '@/lib/utils';

export function ChatLayout() {
  const { isSidebarOpen, isSOAPanelOpen, isSOAMaximized, isSourcesPanelOpen, loadConversations, refreshWorkspaceStatus } = useChatStore();

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

      {/* ── Main chat area ── */}
      <main className="flex flex-1 flex-col overflow-hidden min-w-0">
        {/* Top header bar */}
        <ChatHeader />

        {/* Message area — scrollable */}
        <MessageList />

        {/* Prompt composer — sticky bottom */}
        <PromptComposer />
      </main>

      {/* ── Sources panel ── */}
      <div
        className="transition-all duration-300 ease-in-out shrink-0 overflow-hidden"
        style={{ width: isSourcesPanelOpen ? '360px' : '0px' }}
      >
        <SourcesPanel />
      </div>

      {/* ── SOA artifact panel ── */}
      {isSOAMaximized ? (
        <div className="fixed inset-0 z-50 transition-all duration-300">
          <SOAPanel />
        </div>
      ) : (
        <div
          className="transition-all duration-300 ease-in-out shrink-0 overflow-hidden"
          style={{ width: isSOAPanelOpen ? '480px' : '0px' }}
        >
          <SOAPanel />
        </div>
      )}
    </div>
  );
}
