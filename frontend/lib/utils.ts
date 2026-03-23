import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'] as const;
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'] as const;

export function formatTimestamp(date: Date): string {
  const now = new Date();
  const diff = now.getTime() - date.getTime();
  const days = Math.floor(diff / (1000 * 60 * 60 * 24));

  if (days === 0) {
    // Manual 12-hour format — consistent across server and browser
    const h = date.getHours();
    const m = date.getMinutes().toString().padStart(2, '0');
    const hour12 = h % 12 || 12;
    const period = h < 12 ? 'AM' : 'PM';
    return `${hour12}:${m} ${period}`;
  } else if (days === 1) {
    return 'Yesterday';
  } else if (days < 7) {
    return WEEKDAYS[date.getDay()];
  } else {
    return `${MONTHS[date.getMonth()]} ${date.getDate()}`;
  }
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function generateId(): string {
  return Math.random().toString(36).slice(2, 11);
}
