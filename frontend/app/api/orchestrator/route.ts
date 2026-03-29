/**
 * /api/orchestrator — Next.js route that proxies planning requests to the FastAPI backend.
 *
 * After receiving the plan, injects real storage_refs into any
 * extract_factfind_from_document steps (since the planner LLM cannot reliably
 * copy random ObjectId strings from context).
 */

import { NextRequest, NextResponse } from 'next/server';

const BACKEND = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();

    // Forward to FastAPI planner
    const backendRes = await fetch(`${BACKEND}/api/orchestrator/plan`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });

    if (!backendRes.ok) {
      let detail = `Backend error ${backendRes.status}`;
      try {
        const err = await backendRes.json();
        detail = err?.detail ?? detail;
      } catch { /* ignore */ }
      return NextResponse.json({ error: detail }, { status: backendRes.status });
    }

    const plan = await backendRes.json();

    // Inject real storage_refs — the planner LLM can't reliably copy ObjectIds
    const attachedFiles: Array<{ storage_ref?: string; name?: string }> =
      body?.context?.attachedFiles ?? [];
    const validRefs = attachedFiles
      .map((f) => f.storage_ref)
      .filter((r): r is string => typeof r === 'string' && r.length > 0);

    if (validRefs.length > 0 && Array.isArray(plan.steps)) {
      plan.steps = plan.steps.map((step: { tool_id: string; parameters: Record<string, unknown> }, i: number) => {
        if (step.tool_id === 'extract_factfind_from_document') {
          // Use the matching file by index, or fall back to the first
          const ref = validRefs[i] ?? validRefs[0];
          return {
            ...step,
            parameters: { ...step.parameters, storage_ref: ref },
          };
        }
        return step;
      });
    }

    return NextResponse.json(plan);
  } catch (err) {
    const msg = err instanceof Error ? err.message : 'Orchestrator plan failed';
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}
