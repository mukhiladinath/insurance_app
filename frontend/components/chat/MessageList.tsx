'use client';

import { useEffect, useRef } from 'react';
import { useChatStore } from '@/store/chat-store';
import { mockQuickPrompts } from '@/lib/mock-data';
import { MessageBubble } from './MessageBubble';
import { QuickPrompts } from './QuickPrompts';

export function MessageList() {
  const { messages, isStreaming } = useChatStore();
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isStreaming]);

  const isEmpty = messages.length === 0;

  return (
    <div className="flex-1 overflow-y-auto bg-slate-50/50">
      <div className="mx-auto max-w-3xl py-4">
        {/* Quick prompts shown when chat is empty */}
        {isEmpty && <QuickPrompts prompts={mockQuickPrompts} />}

        {/* Message thread */}
        {!isEmpty && (
          <div className="space-y-5 py-4">
            {messages.map((message) => (
              <MessageBubble key={message.id} message={message} />
            ))}
          </div>
        )}

        {/* Streaming indicator */}
        {isStreaming && (
          <div className="flex items-center gap-3 px-4 py-2">
            <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-indigo-600">
              <span className="text-white text-xs">AI</span>
            </div>
            <div className="flex gap-1 items-center">
              <span className="h-2 w-2 rounded-full bg-slate-400 animate-bounce [animation-delay:0ms]" />
              <span className="h-2 w-2 rounded-full bg-slate-400 animate-bounce [animation-delay:150ms]" />
              <span className="h-2 w-2 rounded-full bg-slate-400 animate-bounce [animation-delay:300ms]" />
            </div>
          </div>
        )}

        {/* Scroll anchor */}
        <div ref={bottomRef} className="h-4" />
      </div>
    </div>
  );
}
