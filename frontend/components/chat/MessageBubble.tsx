'use client';

import { FileText, User, Shield } from 'lucide-react';
import { Message } from '@/lib/types';
import { cn, formatTimestamp, formatFileSize } from '@/lib/utils';

interface MessageBubbleProps {
  message: Message;
}

function renderContent(content: string) {
  const lines = content.split('\n');
  const elements: React.ReactNode[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    if (line.trim() === '') {
      elements.push(<div key={i} className="h-2" />);
      i++;
      continue;
    }

    // Heading ### (must check before ## and #)
    if (line.startsWith('### ')) {
      elements.push(
        <h4 key={i} className="font-semibold text-[12px] mt-2 mb-0.5 text-slate-700 uppercase tracking-wide">
          {line.slice(4)}
        </h4>
      );
      i++;
      continue;
    }

    // Heading ##
    if (line.startsWith('## ')) {
      elements.push(
        <h3 key={i} className="font-bold text-[13px] mt-3 mb-1 text-slate-800">
          {line.slice(3)}
        </h3>
      );
      i++;
      continue;
    }

    // Heading #
    if (line.startsWith('# ')) {
      elements.push(
        <h2 key={i} className="font-bold text-sm mt-3 mb-1 text-slate-900">
          {line.slice(2)}
        </h2>
      );
      i++;
      continue;
    }

    // Bullet list
    if (line.startsWith('- ') || line.startsWith('* ')) {
      elements.push(
        <div key={i} className="flex items-start gap-2 text-[13px]">
          <span className="mt-[5px] h-1.5 w-1.5 rounded-full bg-indigo-400 shrink-0" />
          <span>{renderInline(line.slice(2))}</span>
        </div>
      );
      i++;
      continue;
    }

    // Numbered list
    const numberedMatch = line.match(/^(\d+)\.\s(.+)/);
    if (numberedMatch) {
      elements.push(
        <div key={i} className="flex items-start gap-2 text-[13px]">
          <span className="shrink-0 text-indigo-500 font-semibold min-w-[16px]">
            {numberedMatch[1]}.
          </span>
          <span>{renderInline(numberedMatch[2])}</span>
        </div>
      );
      i++;
      continue;
    }

    // Regular paragraph with inline formatting
    elements.push(
      <p key={i} className="text-[13px] leading-relaxed">
        {renderInline(line)}
      </p>
    );
    i++;
  }

  return <div className="space-y-1">{elements}</div>;
}

function renderInline(text: string): React.ReactNode {
  // Split on **bold** patterns
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return (
    <>
      {parts.map((part, idx) => {
        if (part.startsWith('**') && part.endsWith('**') && part.length > 4) {
          return (
            <strong key={idx} className="font-semibold text-slate-900">
              {part.slice(2, -2)}
            </strong>
          );
        }
        return <span key={idx}>{part}</span>;
      })}
    </>
  );
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === 'user';

  if (isUser) {
    return (
      <div className="flex justify-end px-4 group">
        <div className="flex flex-col items-end gap-1.5 max-w-[75%]">
          {/* Attachments */}
          {message.attachments && message.attachments.length > 0 && (
            <div className="flex flex-wrap gap-2 justify-end mb-1">
              {message.attachments.map((att) => (
                <div
                  key={att.id}
                  className="flex items-center gap-2 rounded-xl bg-indigo-700 px-3 py-2"
                >
                  <FileText size={13} className="text-indigo-200 shrink-0" />
                  <div>
                    <p className="text-[11px] font-medium text-white leading-tight">
                      {att.name}
                    </p>
                    <p className="text-[10px] text-indigo-300">{formatFileSize(att.size)}</p>
                  </div>
                </div>
              ))}
            </div>
          )}
          {/* Message bubble */}
          <div className="rounded-2xl rounded-tr-sm bg-indigo-600 px-4 py-3 shadow-sm">
            <p className="text-[13px] text-white leading-relaxed">{message.content}</p>
          </div>
          <span className="text-[10px] text-slate-400 opacity-0 group-hover:opacity-100 transition-opacity" suppressHydrationWarning>
            {formatTimestamp(message.timestamp)}
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-start gap-3 px-4 group">
      {/* Avatar */}
      <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-indigo-600 shadow-sm mt-0.5">
        <Shield size={13} className="text-white" />
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1.5">
          <span className="text-[11px] font-semibold text-slate-700">Insurance AI</span>
          <span className="text-[10px] text-slate-400 opacity-0 group-hover:opacity-100 transition-opacity" suppressHydrationWarning>
            {formatTimestamp(message.timestamp)}
          </span>
        </div>
        <div className="rounded-2xl rounded-tl-sm bg-white border border-slate-200 px-4 py-3 shadow-sm">
          <div className="text-slate-700">{renderContent(message.content)}</div>
          {message.isStreaming && (
            <span className="inline-block mt-1 h-4 w-1.5 animate-pulse rounded-sm bg-indigo-400" />
          )}
        </div>
      </div>
    </div>
  );
}
