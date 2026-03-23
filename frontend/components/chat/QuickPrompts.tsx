'use client';

import {
  GitCompare,
  ShieldAlert,
  FileText,
  History,
  LucideIcon,
} from 'lucide-react';
import { QuickPrompt } from '@/lib/types';
import { useChatStore } from '@/store/chat-store';
import { cn } from '@/lib/utils';

const iconMap: Record<string, LucideIcon> = {
  GitCompare,
  ShieldAlert,
  FileText,
  History,
};

const categoryColors: Record<string, string> = {
  Analysis: 'text-indigo-500 bg-indigo-50',
  Review: 'text-amber-600 bg-amber-50',
  Documents: 'text-emerald-600 bg-emerald-50',
  History: 'text-violet-600 bg-violet-50',
};

interface QuickPromptsProps {
  prompts: QuickPrompt[];
}

export function QuickPrompts({ prompts }: QuickPromptsProps) {
  const { sendMessage } = useChatStore();

  const handlePromptClick = (prompt: QuickPrompt) => {
    sendMessage(prompt.title);
  };

  return (
    <div className="px-4 pt-6 pb-2">
      {/* Greeting */}
      <div className="mb-5 text-center">
        <div className="inline-flex h-12 w-12 items-center justify-center rounded-2xl bg-indigo-600 shadow-lg shadow-indigo-200 mb-3">
          <ShieldAlert size={22} className="text-white" />
        </div>
        <h2 className="text-lg font-semibold text-slate-800">
          How can I help you today?
        </h2>
        <p className="text-sm text-slate-500 mt-1">
          Start a conversation or choose a quick action below.
        </p>
      </div>

      {/* Cards grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 max-w-2xl mx-auto">
        {prompts.map((prompt) => {
          const Icon = iconMap[prompt.iconName] ?? FileText;
          const colorClass =
            categoryColors[prompt.category] ?? 'text-slate-500 bg-slate-100';

          return (
            <button
              key={prompt.id}
              onClick={() => handlePromptClick(prompt)}
              className={cn(
                'group flex items-start gap-3 rounded-2xl border border-slate-200 bg-white p-4 text-left transition-all duration-200',
                'hover:border-indigo-200 hover:bg-indigo-50/40 hover:shadow-sm active:scale-[0.98]'
              )}
            >
              <div
                className={cn(
                  'flex h-8 w-8 shrink-0 items-center justify-center rounded-xl transition-colors',
                  colorClass
                )}
              >
                <Icon size={15} />
              </div>
              <div className="min-w-0">
                <p className="text-[13px] font-semibold text-slate-800 leading-tight group-hover:text-indigo-700 transition-colors">
                  {prompt.title}
                </p>
                <p className="text-[11px] text-slate-500 mt-1 leading-relaxed">
                  {prompt.description}
                </p>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
