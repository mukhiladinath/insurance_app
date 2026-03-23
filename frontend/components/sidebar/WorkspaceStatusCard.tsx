'use client';

import { Cpu, Wrench, Wifi, WifiOff, Loader2 } from 'lucide-react';
import { WorkspaceStatus } from '@/lib/types';
import { cn } from '@/lib/utils';

interface WorkspaceStatusCardProps {
  status: WorkspaceStatus;
}

const statusConfig = {
  online: {
    label: 'Connected',
    color: 'text-emerald-400',
    dotColor: 'bg-emerald-400',
    icon: Wifi,
  },
  offline: {
    label: 'Disconnected',
    color: 'text-red-400',
    dotColor: 'bg-red-500',
    icon: WifiOff,
  },
  connecting: {
    label: 'Connecting…',
    color: 'text-amber-400',
    dotColor: 'bg-amber-400',
    icon: Loader2,
  },
};

export function WorkspaceStatusCard({ status }: WorkspaceStatusCardProps) {
  const config = statusConfig[status.backend];
  const Icon = config.icon;

  return (
    <div className="mx-3 mb-3 rounded-xl border border-slate-800 bg-slate-900 p-3">
      {/* Status row */}
      <div className="flex items-center justify-between mb-2.5">
        <div className="flex items-center gap-2">
          <span
            className={cn(
              'relative flex h-2 w-2',
              status.backend === 'online' && 'animate-pulse'
            )}
          >
            <span
              className={cn(
                'absolute inline-flex h-full w-full rounded-full opacity-75',
                status.backend === 'online' && 'animate-ping bg-emerald-400'
              )}
            />
            <span
              className={cn(
                'relative inline-flex rounded-full h-2 w-2',
                config.dotColor
              )}
            />
          </span>
          <span className={cn('text-xs font-medium', config.color)}>
            {config.label}
          </span>
        </div>
        <Icon
          size={13}
          className={cn(
            config.color,
            status.backend === 'connecting' && 'animate-spin'
          )}
        />
      </div>

      {/* Info rows */}
      <div className="space-y-1.5">
        <div className="flex items-center gap-2 text-[11px] text-slate-500">
          <Cpu size={11} className="text-slate-600 shrink-0" />
          <span className="truncate">{status.model}</span>
        </div>
        <div className="flex items-center gap-2 text-[11px] text-slate-500">
          <Wrench size={11} className="text-slate-600 shrink-0" />
          <span>{status.toolsAvailable} tools available</span>
        </div>
      </div>
    </div>
  );
}
