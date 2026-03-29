/**
 * /api/orchestrator/summarize — Proxy to FastAPI summarize endpoint.
 */

import { NextRequest, NextResponse } from 'next/server';

const BACKEND = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();

    const backendRes = await fetch(`${BACKEND}/api/orchestrator/summarize`, {
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

    const data = await backendRes.json();
    return NextResponse.json(data);
  } catch (err) {
    const msg = err instanceof Error ? err.message : 'Summarize failed';
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}
