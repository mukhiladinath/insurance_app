"""Unit tests for insurance comparison tool-run ref parsing."""

import pytest
from fastapi import HTTPException

from app.insurance_comparison.service import (
    parse_analysis_output_ref,
    parse_saved_run_step_ref,
)


def test_parse_saved_run_step_ref_ok():
    a, b = parse_saved_run_step_ref("64a1b2c3d4e5f678901234ab:step_0")
    assert a == "64a1b2c3d4e5f678901234ab"
    assert b == "step_0"


def test_parse_saved_run_step_ref_invalid():
    with pytest.raises(HTTPException) as exc:
        parse_saved_run_step_ref("nocolon")
    assert exc.value.status_code == 400


def test_parse_analysis_output_ref_none_for_workspace_style():
    assert parse_analysis_output_ref("64a1b2c3d4e5f678901234ab:step_0") is None


def test_parse_analysis_output_ref_ok():
    out = parse_analysis_output_ref("analysisoutput:64a1b2c3d4e5f678901234ab:1")
    assert out == ("64a1b2c3d4e5f678901234ab", 1)


def test_parse_analysis_output_ref_bad_index():
    with pytest.raises(HTTPException) as exc:
        parse_analysis_output_ref("analysisoutput:64a1b2c3d4e5f678901234ab:x")
    assert exc.value.status_code == 400
