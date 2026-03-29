"""Maps tool_name → normalizer callable."""

from __future__ import annotations

from typing import Any, Callable

from app.insurance_comparison.normalizers.tools import TOOL_NORMALIZERS

NormalizerFn = Callable[..., dict[str, Any]]


def has_normalizer(tool_name: str) -> bool:
    return tool_name in TOOL_NORMALIZERS


def get_normalizer(tool_name: str) -> NormalizerFn | None:
    return TOOL_NORMALIZERS.get(tool_name)


def unwrap_tool_execution_envelope(raw: dict[str, Any]) -> dict[str, Any]:
    """
    POST /api/tools/{tool}/run returns ToolExecutionResult: tool JSON lives in output_payload.
    The finobi orchestrator persists that full JSON; normalizers expect the inner tool shape.
    """
    if not isinstance(raw, dict):
        return raw
    inner = raw.get("output_payload")
    if not isinstance(inner, dict) or not inner:
        return raw
    # Strong signal: FastAPI tool run envelope (see app.schemas.tool.ToolExecutionResult)
    if isinstance(raw.get("tool_name"), str) and isinstance(raw.get("status"), str):
        return inner
    return raw


def normalize_tool_output(
    tool_name: str,
    raw_output: dict[str, Any],
    *,
    tool_run_id: str,
    client_id: str,
    generated_at: str,
) -> dict[str, Any] | None:
    fn = get_normalizer(tool_name)
    if not fn:
        return None
    body = unwrap_tool_execution_envelope(raw_output)
    return fn(body, tool_run_id=tool_run_id, client_id=client_id, generated_at=generated_at)
