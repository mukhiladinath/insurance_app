'use client';

// ---------------------------------------------------------------------------
// Capability cards
// ---------------------------------------------------------------------------

const CAPABILITIES = [
  {
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
      </svg>
    ),
    color: 'text-indigo-600 bg-indigo-50',
    title: 'Analyse Policies',
    description: 'Assess Life, TPD, Income Protection, and Trauma cover. Compare retain vs replace scenarios with premium impact.',
  },
  {
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
      </svg>
    ),
    color: 'text-emerald-600 bg-emerald-50',
    title: 'Generate SOA',
    description: 'Produce a structured Statement of Advice from the conversation. Edit in a rich-text panel and export to PDF or Word.',
  },
  {
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
      </svg>
    ),
    color: 'text-amber-600 bg-amber-50',
    title: 'Review Coverage Gaps',
    description: 'Identify underinsurance and coverage shortfalls. Get recommendations aligned with the client\'s financial position.',
  },
  {
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
      </svg>
    ),
    color: 'text-slate-600 bg-slate-100',
    title: 'Summarise Documents',
    description: 'Upload a policy PDF or DOCX and ask for a plain-English summary. Client facts are automatically extracted into memory.',
  },
];

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function WelcomeScreen() {
  return (
    <div className="px-4 py-8 space-y-6">
      {/* Header */}
      <div className="text-center space-y-1">
        <div className="flex justify-center mb-4">
          <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-indigo-600 shadow-lg shadow-indigo-200">
            <svg className="w-7 h-7 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" />
            </svg>
          </div>
        </div>
        <h1 className="text-xl font-bold text-slate-800">Advisor Workspace</h1>
        <p className="text-sm text-slate-400">Your AI-powered insurance advisory assistant</p>
      </div>

      {/* Capability cards */}
      <div>
        <p className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-3">What I can do</p>
        <div className="grid grid-cols-2 gap-2">
          {CAPABILITIES.map((cap) => (
            <div
              key={cap.title}
              className="flex items-center gap-2.5 rounded-lg border border-slate-100 bg-white px-3 py-2.5"
            >
              <div className={`inline-flex shrink-0 items-center justify-center w-7 h-7 rounded-md ${cap.color}`}>
                {cap.icon}
              </div>
              <div className="min-w-0">
                <p className="text-xs font-semibold text-slate-700">{cap.title}</p>
                <p className="text-[11px] text-slate-400 leading-snug">{cap.description}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
