'use client';

import { useEffect, useRef } from 'react';

// ---------------------------------------------------------------------------
// Command definitions
// ---------------------------------------------------------------------------

export interface SlashCommand {
  id: string;
  label: string;
  description: string;
  prompt: string;         // text inserted into the input
  icon: React.ReactNode;
  category: 'tool' | 'soa';
}

const toolIcon = (
  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M11.42 15.17L17.25 21A2.652 2.652 0 0021 17.25l-5.877-5.877M11.42 15.17l2.496-3.03c.317-.384.74-.626 1.208-.766M11.42 15.17l-4.655 5.653a2.548 2.548 0 11-3.586-3.586l6.837-5.63m5.108-.233c.55-.164 1.163-.188 1.743-.14a4.5 4.5 0 004.486-6.336l-3.276 3.277a3.004 3.004 0 01-2.25-2.25l3.276-3.276a4.5 4.5 0 00-6.336 4.486c.091 1.076-.071 2.264-.904 2.95l-.102.085m-1.745 1.437L5.909 7.5H4.5L2.25 3.75l1.5-1.5L7.5 4.5v1.409l4.26 4.26m-1.745 1.437l1.745-1.437m6.615 8.206L15.75 15.75M4.867 19.125h.008v.008h-.008v-.008z" />
  </svg>
);

const soaIcon = (
  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
  </svg>
);

export const SLASH_COMMANDS: SlashCommand[] = [
  {
    id: 'life-tpd',
    label: 'Analyse Life & TPD Policy',
    description: 'Assess Life and TPD cover — purchase, retain, replace, or supplement',
    prompt: 'Analyse life and TPD insurance for ',
    icon: toolIcon,
    category: 'tool',
  },
  {
    id: 'life-in-super',
    label: 'Analyse Life Insurance in Super',
    description: 'Evaluate life cover held inside superannuation under the PYS framework',
    prompt: 'Analyse life insurance in super for ',
    icon: toolIcon,
    category: 'tool',
  },
  {
    id: 'income-protection',
    label: 'Analyse Income Protection',
    description: 'Assess IP / salary continuance — benefit need, waiting period, and benefit period',
    prompt: 'Analyse income protection insurance for ',
    icon: toolIcon,
    category: 'tool',
  },
  {
    id: 'ip-in-super',
    label: 'Analyse IP in Super',
    description: 'Evaluate income protection held inside superannuation (salary continuance)',
    prompt: 'Analyse income protection in super for ',
    icon: toolIcon,
    category: 'tool',
  },
  {
    id: 'tpd-assessment',
    label: 'Assess TPD Policy',
    description: 'Evaluate TPD definition quality, super vs retail placement, and compliance',
    prompt: 'Assess TPD policy for ',
    icon: toolIcon,
    category: 'tool',
  },
  {
    id: 'tpd-in-super',
    label: 'Analyse TPD in Super',
    description: 'Evaluate TPD cover inside superannuation under the PYS framework',
    prompt: 'Analyse TPD insurance in super for ',
    icon: toolIcon,
    category: 'tool',
  },
  {
    id: 'trauma',
    label: 'Analyse Trauma / Critical Illness',
    description: 'Advise on purchasing, retaining, or replacing trauma / CI cover',
    prompt: 'Analyse trauma insurance for ',
    icon: toolIcon,
    category: 'tool',
  },
  {
    id: 'generate-soa',
    label: 'Generate SOA',
    description: 'Produce a Statement of Advice from this conversation',
    prompt: 'Generate SOA',
    icon: soaIcon,
    category: 'soa',
  },
];

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface SlashMenuProps {
  query: string;            // text after the "/" used to filter
  onSelect: (cmd: SlashCommand) => void;
  onClose: () => void;
  activeIndex: number;
  setActiveIndex: (i: number) => void;
}

export function SlashMenu({ query, onSelect, onClose, activeIndex, setActiveIndex }: SlashMenuProps) {
  const listRef = useRef<HTMLDivElement>(null);

  const filtered = SLASH_COMMANDS.filter(
    (c) =>
      query === '' ||
      c.label.toLowerCase().includes(query.toLowerCase()) ||
      c.description.toLowerCase().includes(query.toLowerCase()),
  );

  // Scroll active item into view
  useEffect(() => {
    const el = listRef.current?.querySelector(`[data-index="${activeIndex}"]`) as HTMLElement | null;
    el?.scrollIntoView({ block: 'nearest' });
  }, [activeIndex]);

  if (filtered.length === 0) return null;

  return (
    <div className="absolute bottom-full left-0 right-0 mb-2 z-50">
      <div className="mx-auto max-w-3xl">
        <div
          ref={listRef}
          className="rounded-xl border border-slate-200 bg-white shadow-xl overflow-hidden max-h-72 overflow-y-auto"
        >
          {/* Header */}
          <div className="flex items-center justify-between px-3 py-2 border-b border-slate-100 bg-slate-50">
            <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Commands</span>
            <span className="text-[10px] text-slate-400">↑↓ navigate · Enter select · Esc close</span>
          </div>

          {filtered.map((cmd, i) => (
            <button
              key={cmd.id}
              data-index={i}
              onClick={() => onSelect(cmd)}
              onMouseEnter={() => setActiveIndex(i)}
              className={[
                'w-full flex items-center gap-3 px-3 py-2.5 text-left transition-colors',
                i === activeIndex ? 'bg-indigo-50' : 'hover:bg-slate-50',
              ].join(' ')}
            >
              {/* Icon */}
              <div className={[
                'flex shrink-0 items-center justify-center w-7 h-7 rounded-lg',
                cmd.category === 'soa' ? 'bg-emerald-100 text-emerald-600' : 'bg-indigo-100 text-indigo-600',
              ].join(' ')}>
                {cmd.icon}
              </div>
              {/* Text */}
              <div className="min-w-0">
                <p className="text-xs font-semibold text-slate-700">{cmd.label}</p>
                <p className="text-[11px] text-slate-400 truncate">{cmd.description}</p>
              </div>
              {/* Prompt preview */}
              <span className="ml-auto shrink-0 text-[10px] text-slate-300 font-mono hidden sm:block truncate max-w-[140px]">
                {cmd.prompt}…
              </span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
