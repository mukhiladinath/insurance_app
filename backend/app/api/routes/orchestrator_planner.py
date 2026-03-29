"""
orchestrator_planner.py — Finobi-style orchestrator planning + summarization endpoints.

The frontend calls these endpoints to:
1. Get a plan from the LLM (planner decides what tools to run and in what order)
2. Summarize tool execution results after the frontend has run the tools

Tools execute on the FRONTEND (Next.js API routes), not here.
This backend only handles LLM inference.

Routes:
  POST /orchestrator/plan            → Return a plan for an instruction
  POST /orchestrator/summarize       → Summarize tool results as prose
  POST /orchestrator/summarize-stream → Streaming SSE version of summarize
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services.planner_service import plan_instruction, summarize_results, SUMMARIZER_SYSTEM_PROMPT
from app.core.llm import get_chat_model_fresh

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/orchestrator", tags=["orchestrator-planner"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class PageContext(BaseModel):
    currentPage: str = "/"
    selectedClientId: str | None = None
    selectedClientName: str | None = None


class ToolStep(BaseModel):
    tool_id: str
    parameters: dict[str, Any] = {}


class ConversationMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class PlanRequest(BaseModel):
    instruction: str
    context: PageContext = PageContext()
    messages: list[ConversationMessage] = []


class PlanResponse(BaseModel):
    type: str  # confirmation_required | qna_answer | clarification_needed | no_plan
    explanation: str | None = None
    step_labels: list[str] = []
    steps: list[ToolStep] = []
    question: str | None = None
    options: list[str] = []
    message: str | None = None


class ToolResult(BaseModel):
    tool_id: str
    parameters: dict[str, Any] = {}
    result: dict[str, Any] | list[Any] | str | None = None
    status: str = "completed"
    error: str | None = None
    duration_ms: int | None = None


class SummarizeRequest(BaseModel):
    instruction: str
    tool_results: list[ToolResult] = []
    messages: list[ConversationMessage] = []


class SummarizeResponse(BaseModel):
    summary: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/plan", response_model=PlanResponse)
async def plan(body: PlanRequest) -> PlanResponse:
    """
    Accept a natural-language instruction and return a structured plan.

    The plan tells the frontend which tools to run, with what parameters,
    and in what order. The frontend then shows the plan to the user for
    confirmation before executing.
    """
    context = body.context.model_dump()
    messages = [m.model_dump() for m in body.messages]

    result = await plan_instruction(
        instruction=body.instruction,
        context=context,
        messages=messages,
    )

    # Parse steps from the raw plan dict
    raw_steps = result.get("steps", [])
    steps = [
        ToolStep(
            tool_id=s.get("tool_id", ""),
            parameters=s.get("parameters", {}),
        )
        for s in raw_steps
        if isinstance(s, dict) and s.get("tool_id")
    ]

    return PlanResponse(
        type=result.get("type", "no_plan"),
        explanation=result.get("explanation"),
        step_labels=result.get("step_labels", []),
        steps=steps,
        question=result.get("question"),
        options=result.get("options", []),
        message=result.get("message"),
    )


@router.post("/summarize", response_model=SummarizeResponse)
async def summarize(body: SummarizeRequest) -> SummarizeResponse:
    """
    Generate a prose summary of tool execution results.
    Called by the frontend after tool steps have been executed.
    """
    tool_results_raw = [r.model_dump() for r in body.tool_results]
    messages_raw = [m.model_dump() for m in body.messages]

    summary = await summarize_results(
        instruction=body.instruction,
        tool_results=tool_results_raw,
        messages=messages_raw,
    )

    return SummarizeResponse(summary=summary)


@router.post("/summarize-stream")
async def summarize_stream(body: SummarizeRequest):
    """
    Streaming SSE version of the summarizer.
    Yields tokens as they arrive from the LLM.

    SSE format:
      data: {"token": "..."}\n\n
      data: {"done": true}\n\n
    """
    tool_results_raw = [r.model_dump() for r in body.tool_results]

    results_text = json.dumps(tool_results_raw, indent=2, default=str)
    if len(results_text) > 8000:
        results_text = results_text[:8000] + "\n... [truncated]"

    history_text = ""
    if body.messages:
        recent = body.messages[-4:]
        lines = [f"{m.role.upper()}: {m.content}" for m in recent]
        if lines:
            history_text = "\nRecent conversation:\n" + "\n".join(lines) + "\n"

    user_prompt = f"""\
Original instruction: {body.instruction}
{history_text}
Tool results:
{results_text}

Provide a clear, professional summary for the insurance adviser."""

    async def event_generator():
        try:
            llm = get_chat_model_fresh(temperature=0.2)
            messages = [
                {"role": "system", "content": SUMMARIZER_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ]

            async for chunk in llm.astream(messages):
                token = chunk.content if hasattr(chunk, "content") else str(chunk)
                if token:
                    payload = json.dumps({"token": token})
                    yield f"data: {payload}\n\n"

            yield f"data: {json.dumps({'done': True})}\n\n"

        except Exception as exc:
            logger.error("summarize-stream error: %s", exc)
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
