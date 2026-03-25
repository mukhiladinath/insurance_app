import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Parse an ISO datetime string from the backend as UTC.
 * MongoDB/Pydantic may omit the trailing "Z", causing JS to parse as local time.
 * This always appends "Z" if no timezone designator is present.
 */
export function parseUTCDate(s: string | Date): Date {
  if (s instanceof Date) return s;
  // Already has timezone info (+HH:MM or Z)
  if (s.endsWith('Z') || /[+-]\d{2}:\d{2}$/.test(s)) return new Date(s);
  return new Date(s + 'Z');
}

const IST = 'Asia/Kolkata';

/** Returns "YYYY-MM-DD" in IST for date comparison. */
function istDateKey(date: Date): string {
  return date.toLocaleDateString('en-CA', { timeZone: IST }); // en-CA gives YYYY-MM-DD
}

/**
 * Format a timestamp relative to now, always in IST (UTC+5:30).
 *  - Today     → "3:45 PM"
 *  - Yesterday → "Yesterday"
 *  - < 7 days  → "Mon" / "Tue" …
 *  - Older     → "Mar 21"
 */
export function formatTimestamp(date: Date): string {
  const now = new Date();
  const todayKey     = istDateKey(now);
  const dateKey      = istDateKey(date);

  const yesterday = new Date(now);
  yesterday.setDate(yesterday.getDate() - 1);
  const yesterdayKey = istDateKey(yesterday);

  if (dateKey === todayKey) {
    return date.toLocaleTimeString('en-IN', {
      timeZone: IST,
      hour: '2-digit',
      minute: '2-digit',
      hour12: true,
    });
  }

  if (dateKey === yesterdayKey) return 'Yesterday';

  const diffMs   = now.getTime() - date.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays < 7) {
    return date.toLocaleDateString('en-IN', { timeZone: IST, weekday: 'short' });
  }

  return date.toLocaleDateString('en-IN', { timeZone: IST, day: 'numeric', month: 'short' });
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function generateId(): string {
  return Math.random().toString(36).slice(2, 11);
}
