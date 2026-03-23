import { Chat, Message, QuickPrompt, WorkspaceStatus } from './types';

export const mockChats: Chat[] = [
  {
    id: 'chat-1',
    title: 'Smith Family — Policy Review',
    lastMessage: 'Retain vs replace analysis complete. Recommendation: replace.',
    timestamp: new Date('2026-03-22T10:30:00'),
    messageCount: 8,
  },
  {
    id: 'chat-2',
    title: 'Johnson — TPD Coverage Gap',
    lastMessage: 'TPD sum insured appears underinsured relative to liabilities.',
    timestamp: new Date('2026-03-21T14:15:00'),
    messageCount: 12,
  },
  {
    id: 'chat-3',
    title: 'Life Insurance in Super Analysis',
    lastMessage: 'The client\'s existing super fund cover needs review.',
    timestamp: new Date('2026-03-20T09:00:00'),
    messageCount: 5,
  },
  {
    id: 'chat-4',
    title: 'Williams — SOA Draft',
    lastMessage: 'SOA draft prepared and ready for your review.',
    timestamp: new Date('2026-03-19T16:45:00'),
    messageCount: 15,
  },
  {
    id: 'chat-5',
    title: 'Income Protection Review',
    lastMessage: '90-day wait period compared across three providers.',
    timestamp: new Date('2026-03-18T11:20:00'),
    messageCount: 9,
  },
  {
    id: 'chat-6',
    title: 'New Client Onboarding',
    lastMessage: 'Initial fact-find captured. Ready for needs analysis.',
    timestamp: new Date('2026-03-15T13:00:00'),
    messageCount: 4,
  },
  {
    id: 'chat-7',
    title: 'Trauma Cover — Chen Family',
    lastMessage: 'Trauma event definitions reviewed across shortlisted policies.',
    timestamp: new Date('2026-03-12T09:45:00'),
    messageCount: 7,
  },
];

export const mockMessages: Message[] = [
  {
    id: 'msg-1',
    role: 'assistant',
    content: `Welcome back. I'm your Insurance Advisory AI — ready to help you analyse policies, review coverage gaps, run retain vs replace comparisons, and prepare SOA recommendations.

How can I assist with the Smith family today?`,
    timestamp: new Date('2026-03-22T10:00:00'),
  },
  {
    id: 'msg-2',
    role: 'user',
    content: "I've uploaded the current policy documents for the Smith family. Can you analyse their TPD coverage and identify any gaps?",
    timestamp: new Date('2026-03-22T10:05:00'),
    attachments: [
      {
        id: 'att-1',
        name: 'Smith_CurrentPolicy_2026.pdf',
        type: 'application/pdf',
        size: 245000,
      },
    ],
  },
  {
    id: 'msg-3',
    role: 'assistant',
    content: `Based on the uploaded documents, here is the TPD coverage assessment for the Smith family:

**Current Coverage**
- Life Cover: $850,000 (adequate for current liabilities)
- TPD Cover: $350,000 — any occupation definition
- Income Protection: $6,500/month, 90-day wait period
- Trauma Cover: None

**Identified Gaps**

1. **TPD Definition Risk** — The current policy uses an "any occupation" definition. Given Mr Smith's specialised role as a surgeon, this is materially more restrictive than "own occupation" and represents a significant coverage gap.

2. **TPD Sum Insured** — At $350,000, the TPD cover falls short relative to outstanding mortgage ($620,000) and ongoing lifestyle costs.

3. **No Trauma Cover** — The family has no critical illness protection. Given age and health profile, this is a notable gap.

**Recommended Next Steps**
- Run retain vs replace analysis to assess TPD definition change
- Model increased TPD sum insured ($750,000–$900,000 range)
- Explore trauma cover addition ($300,000 recommended starting point)

Would you like me to run the retain vs replace analysis now?`,
    timestamp: new Date('2026-03-22T10:08:00'),
  },
  {
    id: 'msg-4',
    role: 'user',
    content: 'Yes — run the retain vs replace analysis and include the premium impact.',
    timestamp: new Date('2026-03-22T10:15:00'),
  },
  {
    id: 'msg-5',
    role: 'assistant',
    content: `**Retain vs Replace Analysis — Smith Family TPD**

Running comparison with "own occupation" TPD definition across shortlisted insurers...

**Option A — Retain (Policy Modification)**
- Annual Premium: $4,280
- TPD Definition: Own Occupation (post-modification)
- Sum Insured: $750,000
- Exclusion: Pre-existing back condition applies (added on modification)

**Option B — Replace (New Policy)**
- Annual Premium: $3,950
- TPD Definition: Own Occupation
- Sum Insured: $750,000
- Exclusions: None

**Recommendation: Replace**

The replacement option is $330/year cheaper, eliminates the pre-existing exclusion that would apply on modification, and activates immediately. The existing policy also carries 3-year age loadings that make it progressively less competitive.

Shall I draft the SOA section for this recommendation?`,
    timestamp: new Date('2026-03-22T10:22:00'),
  },
];

export const mockQuickPrompts: QuickPrompt[] = [
  {
    id: 'qp-1',
    title: 'Analyse Retain vs Replace',
    description: 'Compare current policy against replacement options with premium impact',
    iconName: 'GitCompare',
    category: 'Analysis',
  },
  {
    id: 'qp-2',
    title: 'Review Life / TPD Gap',
    description: 'Identify coverage shortfalls and underinsurance risks for a client',
    iconName: 'ShieldAlert',
    category: 'Review',
  },
  {
    id: 'qp-3',
    title: 'Summarise Policy Document',
    description: 'Extract key terms, coverage details, and exclusions from uploaded PDFs',
    iconName: 'FileText',
    category: 'Documents',
  },
  {
    id: 'qp-4',
    title: 'Show Recommendation History',
    description: 'View prior SOA recommendations and their outcomes for this client',
    iconName: 'History',
    category: 'History',
  },
];

export const mockWorkspaceStatus: WorkspaceStatus = {
  backend: 'online',
  model: 'Insurance AI v2',
  toolsAvailable: 6,
  lastSync: new Date(),
};
