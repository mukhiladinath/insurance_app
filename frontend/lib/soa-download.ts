import type { SOASection } from './types';

// ---------------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------------

const SUBSECTIONS = [
  { key: 'our_recommendation' as const,  heading: 'Our Recommendation' },
  { key: 'why_appropriate'   as const,  heading: 'Why Our Advice is Appropriate' },
  { key: 'what_to_consider'  as const,  heading: 'What You Need to Consider' },
  { key: 'more_information'  as const,  heading: 'More Information' },
];

function triggerDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

// ---------------------------------------------------------------------------
// PDF  — jsPDF, text-based (selectable, proper pages)
// ---------------------------------------------------------------------------

export async function downloadSOAasPDF(sections: SOASection[], filename = 'Statement-of-Advice.pdf') {
  const { default: jsPDF } = await import('jspdf');

  const doc = new jsPDF({ orientation: 'p', unit: 'mm', format: 'a4' });
  const pageH   = doc.internal.pageSize.getHeight();
  const pageW   = doc.internal.pageSize.getWidth();
  const margin  = 20;
  const maxW    = pageW - margin * 2;
  let y = margin;

  const newPageIfNeeded = (needed: number) => {
    if (y + needed > pageH - margin) {
      doc.addPage();
      y = margin;
    }
  };

  // ── Document title ──────────────────────────────────────────────────────
  doc.setFontSize(16);
  doc.setFont('helvetica', 'bold');
  doc.setTextColor(30, 58, 95);
  const titleLines = doc.splitTextToSize('Statement of Advice — Insurance Recommendations', maxW);
  doc.text(titleLines, margin, y);
  y += titleLines.length * 8 + 4;

  // Thin rule under title
  doc.setDrawColor(200, 210, 230);
  doc.line(margin, y, pageW - margin, y);
  y += 8;

  for (const section of sections) {
    newPageIfNeeded(22);

    // ── Section heading (H2) ───────────────────────────────────────────
    doc.setFontSize(13);
    doc.setFont('helvetica', 'bold');
    doc.setTextColor(30, 64, 175);
    const secLines = doc.splitTextToSize(section.title, maxW);
    doc.text(secLines, margin, y);
    y += secLines.length * 6 + 1;

    doc.setDrawColor(219, 234, 254);
    doc.line(margin, y, pageW - margin, y);
    y += 5;

    for (const sub of SUBSECTIONS) {
      const text = section[sub.key] ?? '';
      if (!text.trim()) continue;

      newPageIfNeeded(14);

      // Sub-heading (H3)
      doc.setFontSize(10);
      doc.setFont('helvetica', 'bold');
      doc.setTextColor(55, 65, 81);
      doc.text(sub.heading, margin, y);
      y += 5;

      // Body text
      doc.setFontSize(9);
      doc.setFont('helvetica', 'normal');
      doc.setTextColor(75, 85, 99);
      const bodyLines = doc.splitTextToSize(
        text.replace(/\[\[MISSING:[^\]]+\]\]/g, '[Missing]'),
        maxW,
      );
      newPageIfNeeded(bodyLines.length * 4.5);
      doc.text(bodyLines, margin, y);
      y += bodyLines.length * 4.5 + 5;
    }

    y += 6;
  }

  doc.save(filename);
}

// ---------------------------------------------------------------------------
// Word (.docx)  — docx library, structured headings
// ---------------------------------------------------------------------------

export async function downloadSOAasWord(sections: SOASection[], filename = 'Statement-of-Advice.docx') {
  const { Document, Packer, Paragraph, TextRun, HeadingLevel, BorderStyle } = await import('docx');

  const children: InstanceType<typeof Paragraph>[] = [];

  // Document title
  children.push(
    new Paragraph({
      children: [new TextRun({ text: 'Statement of Advice — Insurance Recommendations', bold: true })],
      heading: HeadingLevel.HEADING_1,
      spacing: { after: 200 },
      border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: 'C8D2E6', space: 4 } },
    }),
  );

  for (const section of sections) {
    // Section heading
    children.push(
      new Paragraph({
        text: section.title,
        heading: HeadingLevel.HEADING_2,
        spacing: { before: 320, after: 80 },
      }),
    );

    for (const sub of SUBSECTIONS) {
      const text = section[sub.key] ?? '';
      if (!text.trim()) continue;

      // Sub-heading
      children.push(
        new Paragraph({
          text: sub.heading,
          heading: HeadingLevel.HEADING_3,
          spacing: { before: 200, after: 60 },
        }),
      );

      // Body — split on double newlines into separate paragraphs
      const paras = text
        .replace(/\[\[MISSING:[^\]]+\]\]/g, '[Missing]')
        .split(/\n\n+/)
        .map((p) => p.trim())
        .filter(Boolean);

      for (const para of paras) {
        children.push(
          new Paragraph({
            children: [new TextRun({ text: para, size: 22 })],
            spacing: { after: 100 },
          }),
        );
      }
    }
  }

  const doc = new Document({ sections: [{ children }] });
  const blob = await Packer.toBlob(doc);
  triggerDownload(blob, filename);
}
