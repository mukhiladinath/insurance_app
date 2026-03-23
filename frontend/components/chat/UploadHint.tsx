'use client';

import { CloudUpload, FileText, Image, FileCode2 } from 'lucide-react';
import { cn } from '@/lib/utils';

const supportedTypes = [
  { label: 'PDF', icon: FileText, color: 'text-red-500 bg-red-50' },
  { label: 'DOCX', icon: FileCode2, color: 'text-blue-500 bg-blue-50' },
  { label: 'Image', icon: Image, color: 'text-emerald-500 bg-emerald-50' },
];

interface UploadHintProps {
  isDragging?: boolean;
}

export function UploadHint({ isDragging = false }: UploadHintProps) {
  return (
    <div
      className={cn(
        'flex flex-col items-center gap-2 rounded-xl border-2 border-dashed px-4 py-4 transition-all duration-200',
        isDragging
          ? 'border-indigo-400 bg-indigo-50/60 scale-[1.01]'
          : 'border-slate-200 bg-slate-50/60 hover:border-slate-300'
      )}
    >
      <CloudUpload
        size={20}
        className={cn(
          'transition-colors',
          isDragging ? 'text-indigo-500' : 'text-slate-400'
        )}
      />
      <div className="text-center">
        <p className="text-[12px] font-medium text-slate-600">
          {isDragging ? 'Drop files to attach' : 'Drag & drop files here'}
        </p>
        <p className="text-[11px] text-slate-400 mt-0.5">or use the button below</p>
      </div>
      {/* File type badges */}
      <div className="flex items-center gap-1.5">
        {supportedTypes.map(({ label, icon: Icon, color }) => (
          <div
            key={label}
            className={cn(
              'flex items-center gap-1 rounded-full px-2.5 py-1 text-[10px] font-medium',
              color
            )}
          >
            <Icon size={9} />
            {label}
          </div>
        ))}
      </div>
    </div>
  );
}
