'use client';

import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

type Props = {
  content: string;
  className?: string;
};

/**
 * Renders markdown (including GFM tables, lists, bold) for LLM summaries and memory docs.
 */
export default function MarkdownProse({ content, className = '' }: Props) {
  return (
    <div className={`markdown-prose text-sm text-slate-700 ${className}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children }) => (
            <h1 className="text-lg font-bold text-slate-900 mt-4 mb-2 first:mt-0">{children}</h1>
          ),
          h2: ({ children }) => (
            <h2 className="text-base font-semibold text-slate-800 mt-4 mb-2 first:mt-0">{children}</h2>
          ),
          h3: ({ children }) => (
            <h3 className="text-sm font-semibold text-slate-800 mt-3 mb-1">{children}</h3>
          ),
          h4: ({ children }) => (
            <h4 className="text-sm font-medium text-slate-700 mt-2 mb-1">{children}</h4>
          ),
          p: ({ children }) => (
            <p className="leading-relaxed mb-2 last:mb-0">{children}</p>
          ),
          ul: ({ children }) => (
            <ul className="list-disc pl-5 space-y-1 my-2">{children}</ul>
          ),
          ol: ({ children }) => (
            <ol className="list-decimal pl-5 space-y-1 my-2">{children}</ol>
          ),
          li: ({ children }) => <li className="leading-relaxed">{children}</li>,
          strong: ({ children }) => (
            <strong className="font-semibold text-slate-900">{children}</strong>
          ),
          em: ({ children }) => <em className="italic text-slate-700">{children}</em>,
          a: ({ href, children }) => (
            <a
              href={href}
              className="text-indigo-600 hover:text-indigo-800 underline underline-offset-2"
              target="_blank"
              rel="noreferrer"
            >
              {children}
            </a>
          ),
          blockquote: ({ children }) => (
            <blockquote className="border-l-4 border-slate-200 pl-3 my-2 text-slate-600 italic">
              {children}
            </blockquote>
          ),
          hr: () => <hr className="my-4 border-slate-200" />,
          table: ({ children }) => (
            <div className="overflow-x-auto my-3 rounded-lg border border-slate-200">
              <table className="min-w-full text-xs border-collapse">{children}</table>
            </div>
          ),
          thead: ({ children }) => <thead className="bg-slate-50">{children}</thead>,
          th: ({ children }) => (
            <th className="border-b border-slate-200 px-3 py-2 text-left font-semibold text-slate-700">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="border-b border-slate-100 px-3 py-2 align-top">{children}</td>
          ),
          tr: ({ children }) => <tr className="even:bg-slate-50/50">{children}</tr>,
          pre: ({ children }) => (
            <pre className="bg-slate-900 text-slate-100 p-3 rounded-lg overflow-x-auto text-xs my-2">
              {children}
            </pre>
          ),
          code: ({ className, children, ...props }) => {
            const isFenced = Boolean(className?.startsWith('language-'));
            if (isFenced) {
              return (
                <code className={`text-slate-100 font-mono ${className ?? ''}`} {...props}>
                  {children}
                </code>
              );
            }
            return (
              <code
                className="bg-slate-100 text-slate-800 px-1.5 py-0.5 rounded text-xs font-mono"
                {...props}
              >
                {children}
              </code>
            );
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
