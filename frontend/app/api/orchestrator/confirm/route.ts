/**
 * /api/orchestrator/confirm — Execute tool steps on the frontend and summarize results.
 *
 * Supports two modes:
 *   1. Fresh execution  — steps + step_labels + messages + clientId
 *   2. Resume execution — same as above plus resume_from_index + prior_step_results
 *      (used when a step was paused for a missing critical field)
 *
 * When a step returns a _missing_fields signal, execution pauses and this route
 * returns { type: 'missing_fields', ... } so the store can collect the value.
 */

import { NextRequest, NextResponse } from 'next/server';
import { TOOL_HANDLERS, resolveParameters } from '@/lib/tools/orchestrator-handlers';
import type { ToolContext } from '@/lib/tools/orchestrator-handlers';
import type { MissingFieldsSignal } from '@/lib/tools/orchestrator-handlers';
import { runIncludesAnalysisTool } from '@/lib/orchestrator-analysis-tools';

const BACKEND = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

type StepRecord = {
  tool_id: string;
  step_index: number;
  label: string;
  status: 'completed' | 'failed';
  result: unknown;
  error: string | null;
  duration_ms: number;
};

interface ConfirmRequest {
  instruction: string;
  steps: Array<{ tool_id: string; parameters: Record<string, unknown> }>;
  step_labels: string[];
  messages: Array<{ role: string; content: string }>;
  clientId?: string | null;
  // Resume fields (optional)
  resume_from_index?: number;
  prior_step_results?: StepRecord[];
}

export async function POST(req: NextRequest) {
  try {
    const body: ConfirmRequest = await req.json();
    const {
      instruction,
      steps,
      step_labels,
      messages,
      clientId,
      resume_from_index = 0,
      prior_step_results = [],
    } = body;

    if (!steps || steps.length === 0) {
      return NextResponse.json({ error: 'No steps to execute' }, { status: 400 });
    }

    const ctx: ToolContext = { clientId };

    // Pre-populate results with prior completed steps (for resume mode)
    const stepResults: StepRecord[] = [...prior_step_results];

    for (let i = resume_from_index; i < steps.length; i++) {
      const step = steps[i];
      const label = step_labels[i] ?? step.tool_id;
      const handler = TOOL_HANDLERS[step.tool_id];

      if (!handler) {
        stepResults.push({
          tool_id: step.tool_id,
          step_index: i,
          label,
          status: 'failed',
          result: null,
          error: `Unknown tool: ${step.tool_id}`,
          duration_ms: 0,
        });
        continue;
      }

      // Resolve {{stepN.fieldName}} references from prior results
      const resolvedParams = resolveParameters(
        step.parameters,
        stepResults.map((r) => ({ result: r.result })),
      );

      const toolResult = await handler(resolvedParams, ctx);

      // Check for missing-fields pause signal
      if (
        toolResult.status === 'success' &&
        toolResult.data &&
        typeof toolResult.data === 'object' &&
        (toolResult.data as MissingFieldsSignal)._missing_fields === true
      ) {
        const signal = toolResult.data as MissingFieldsSignal;
        // Return a pause response — execution will resume after user provides values
        return NextResponse.json({
          type: 'missing_fields',
          missing_fields: signal.missing_fields,
          paused_at_index: i,
          prior_step_results: stepResults, // results collected so far (before the paused step)
          steps,
          step_labels,
        });
      }

      stepResults.push({
        tool_id: step.tool_id,
        step_index: i,
        label,
        status: toolResult.status === 'success' ? 'completed' : 'failed',
        result: toolResult.data ?? null,
        error: toolResult.error ?? null,
        duration_ms: toolResult.duration_ms ?? 0,
      });
    }

    // Build tool_results payload for the summarizer
    const toolResultsForSummary = stepResults.map((r) => ({
      tool_id: r.tool_id,
      parameters: steps[r.step_index]?.parameters ?? {},
      result: r.result,
      status: r.status,
      error: r.error,
    }));

    // Get summary from FastAPI
    let summary = '';
    try {
      const summaryRes = await fetch(`${BACKEND}/api/orchestrator/summarize`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          instruction,
          tool_results: toolResultsForSummary,
          messages: messages.slice(-6),
        }),
      });

      if (summaryRes.ok) {
        const summaryData = await summaryRes.json();
        summary = summaryData.summary ?? '';
      }
    } catch (err) {
      // Non-fatal — results still returned without summary
      console.error('summarize call failed:', err);
    }

    const responseBody = {
      type: 'execution_complete' as const,
      step_results: stepResults,
      synthesized_response: summary,
    };

    // Persist LLM summary when an analysis tool completed successfully
    if (
      clientId &&
      runIncludesAnalysisTool(stepResults) &&
      (summary.trim() || stepResults.some((r) => r.status === 'completed'))
    ) {
      const toolIds = [...new Set(stepResults.map((r) => r.tool_id))];
      const labels = stepResults.map((r) => r.label);
      const content =
        summary.trim() ||
        '_No summary was generated; expand the step results above or re-run with a shorter plan._';
      try {
        await fetch(`${BACKEND}/api/clients/${clientId}/analysis-outputs`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            instruction,
            tool_ids: toolIds,
            step_labels: labels,
            content,
          }),
        });
      } catch (e) {
        console.error('Failed to persist analysis output:', e);
      }
    }

    return NextResponse.json(responseBody);
  } catch (err) {
    const msg = err instanceof Error ? err.message : 'Execution failed';
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}
