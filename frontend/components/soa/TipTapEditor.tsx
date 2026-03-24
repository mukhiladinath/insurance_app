'use client';

import { useEditor, EditorContent } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import { useEffect } from 'react';
import type { SOASection } from '@/lib/types';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Convert an array of SOA sections into a single HTML string
 * that TipTap can render and the user can edit.
 *
 * [[MISSING: question]] tokens are rendered as styled inline spans.
 */
function sectionsToHtml(sections: SOASection[]): string {
  if (sections.length === 0) return '<p>No content generated yet.</p>';

  const escape = (s: string) =>
    s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

  const highlightMissing = (text: string): string =>
    escape(text).replace(
      /\[\[MISSING:\s*([^\]]+)\]\]/g,
      (_match, q) =>
        `<mark style="background:#fef08a;border-radius:3px;padding:1px 4px;font-style:italic">[Missing: ${escape(q)}]</mark>`,
    );

  const paragraphs = (text: string): string =>
    text
      .split(/\n\n+/)
      .map((p) => `<p>${highlightMissing(p.trim())}</p>`)
      .join('');

  const parts: string[] = [
    `<h1>Statement of Advice — Insurance Recommendations</h1>`,
  ];

  for (const section of sections) {
    parts.push(`<h2>${escape(section.title)}</h2>`);

    parts.push(`<h3>Our Recommendation</h3>`);
    parts.push(paragraphs(section.our_recommendation));

    parts.push(`<h3>Why Our Advice is Appropriate</h3>`);
    parts.push(paragraphs(section.why_appropriate));

    parts.push(`<h3>What You Need to Consider</h3>`);
    parts.push(paragraphs(section.what_to_consider));

    parts.push(`<h3>More Information</h3>`);
    parts.push(paragraphs(section.more_information));
  }

  return parts.join('\n');
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface TipTapEditorProps {
  sections: SOASection[];
  /** Called with the latest HTML whenever the user edits */
  onChange?: (html: string) => void;
}

export function TipTapEditor({ sections, onChange }: TipTapEditorProps) {
  const editor = useEditor({
    immediatelyRender: false,
    extensions: [
      StarterKit.configure({
        heading: { levels: [1, 2, 3] },
      }),
    ],
    content: sectionsToHtml(sections),
    editorProps: {
      attributes: {
        class: 'prose prose-sm max-w-none focus:outline-none px-6 py-4',
      },
    },
    onUpdate: ({ editor }) => {
      onChange?.(editor.getHTML());
    },
  });

  // Re-populate when sections change (e.g. after user submits answers)
  useEffect(() => {
    if (editor && !editor.isDestroyed) {
      const newHtml = sectionsToHtml(sections);
      // Only update if content actually differs to avoid cursor jump
      if (editor.getHTML() !== newHtml) {
        editor.commands.setContent(newHtml);
      }
    }
  }, [sections, editor]);

  return (
    <div className="h-full overflow-y-auto bg-white rounded-lg border border-slate-200">
      {/* Minimal toolbar */}
      {editor && (
        <div className="flex items-center gap-1 px-3 py-2 border-b border-slate-200 bg-slate-50 sticky top-0 z-10">
          <ToolbarButton
            onClick={() => editor.chain().focus().toggleBold().run()}
            active={editor.isActive('bold')}
            title="Bold"
          >
            <strong>B</strong>
          </ToolbarButton>
          <ToolbarButton
            onClick={() => editor.chain().focus().toggleItalic().run()}
            active={editor.isActive('italic')}
            title="Italic"
          >
            <em>I</em>
          </ToolbarButton>
          <div className="w-px h-4 bg-slate-300 mx-1" />
          <ToolbarButton
            onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}
            active={editor.isActive('heading', { level: 2 })}
            title="Section heading"
          >
            H2
          </ToolbarButton>
          <ToolbarButton
            onClick={() => editor.chain().focus().toggleHeading({ level: 3 }).run()}
            active={editor.isActive('heading', { level: 3 })}
            title="Sub-heading"
          >
            H3
          </ToolbarButton>
          <div className="w-px h-4 bg-slate-300 mx-1" />
          <ToolbarButton
            onClick={() => editor.chain().focus().toggleBulletList().run()}
            active={editor.isActive('bulletList')}
            title="Bullet list"
          >
            ≡
          </ToolbarButton>
        </div>
      )}

      <EditorContent editor={editor} />

      <style>{`
        .ProseMirror h1 { font-size: 1.25rem; font-weight: 700; margin: 1.25rem 0 0.5rem; color: #1e3a5f; }
        .ProseMirror h2 { font-size: 1.05rem; font-weight: 700; margin: 1.5rem 0 0.4rem; color: #1e40af; border-bottom: 1px solid #dbeafe; padding-bottom: 0.2rem; }
        .ProseMirror h3 { font-size: 0.9rem; font-weight: 600; margin: 1rem 0 0.25rem; color: #374151; }
        .ProseMirror p  { margin: 0.35rem 0; font-size: 0.85rem; line-height: 1.6; color: #374151; }
        .ProseMirror ul { list-style: disc; padding-left: 1.25rem; margin: 0.35rem 0; font-size: 0.85rem; }
        .ProseMirror li { margin: 0.15rem 0; }
        .ProseMirror mark { background: #fef08a; border-radius: 3px; padding: 1px 4px; font-style: italic; }
      `}</style>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tiny toolbar button
// ---------------------------------------------------------------------------

function ToolbarButton({
  onClick,
  active,
  title,
  children,
}: {
  onClick: () => void;
  active: boolean;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      className={[
        'px-2 py-0.5 rounded text-xs font-mono transition-colors',
        active
          ? 'bg-indigo-100 text-indigo-700'
          : 'text-slate-500 hover:bg-slate-100 hover:text-slate-700',
      ].join(' ')}
    >
      {children}
    </button>
  );
}
