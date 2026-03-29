"""Pydantic models for API responses (Mongo stores plain dicts)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ComparisonFactModel(BaseModel):
    key: str
    label: str
    category: str
    value: str | float | int | bool | None = None
    displayValue: str = ""
    unit: str | None = None
    comparable: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class ScenarioSummaryModel(BaseModel):
    title: str = ""
    description: str = ""
    recommendationType: str = ""


class CoverSliceModel(BaseModel):
    life: float | None = None
    tpd: float | None = None
    trauma: float | None = None
    incomeProtectionMonthly: float | None = None
    incomeProtectionReplacementRatio: float | None = None
    waitingPeriod: str | None = None
    benefitPeriod: str | None = None
    ownOccupationTPD: bool | None = None
    anyOccupationTPD: bool | None = None
    heldInsideSuper: bool | None = None
    splitOwnership: bool | None = None


class PremiumsSliceModel(BaseModel):
    monthly: float | None = None
    annual: float | None = None
    fundedFromSuper: float | None = None
    fundedPersonally: float | None = None
    deductiblePersonally: bool | None = None
    taxImpactEstimate: float | None = None


class StructuralSliceModel(BaseModel):
    owner: Literal["super", "personal", "split"] | None = None
    insurer: str | None = None
    fundName: str | None = None
    policyType: str | None = None
    steppedOrLevel: str | None = None
    replacementInvolved: bool | None = None
    underwritingRequired: bool | None = None


class SuitabilitySliceModel(BaseModel):
    affordabilityScore: float | None = None
    adequacyScore: float | None = None
    flexibilityScore: float | None = None
    taxEfficiencyScore: float | None = None
    claimsPracticalityScore: float | None = None
    implementationEaseScore: float | None = None


class TradeoffModel(BaseModel):
    category: str
    impact: Literal["better", "worse", "same", "unknown"]
    summary: str


class RiskModel(BaseModel):
    severity: Literal["low", "medium", "high"]
    type: str
    message: str


class ComparisonReadyToolOutputModel(BaseModel):
    toolName: str
    toolRunId: str
    strategyName: str = ""
    clientId: str = ""
    generatedAt: str = ""

    scenarioSummary: ScenarioSummaryModel = Field(default_factory=ScenarioSummaryModel)
    comparisonFacts: list[ComparisonFactModel] = Field(default_factory=list)

    cover: CoverSliceModel = Field(default_factory=CoverSliceModel)
    premiums: PremiumsSliceModel = Field(default_factory=PremiumsSliceModel)
    structural: StructuralSliceModel = Field(default_factory=StructuralSliceModel)
    suitability: SuitabilitySliceModel = Field(default_factory=SuitabilitySliceModel)

    tradeoffs: list[TradeoffModel] = Field(default_factory=list)
    risks: list[RiskModel] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    explanation: str = ""


class FactTableRowModel(BaseModel):
    group: str
    key: str
    label: str
    leftValue: str | float | int | bool | None = None
    rightValue: str | float | int | bool | None = None
    leftDisplay: str = ""
    rightDisplay: str = ""
    delta: float | None = None
    deltaType: Literal["increase", "decrease", "same", "not_applicable"] | None = None
    differenceSummary: str = ""
    betterSide: Literal["left", "right", "neutral", "unknown"] = "unknown"
    comparable: bool = True


class InsightsModel(BaseModel):
    majorDifferences: list[str] = Field(default_factory=list)
    affordability: str = ""
    adequacy: str = ""
    tax: str = ""
    structure: str = ""
    implementationRisk: str = ""
    claimsPracticality: str = ""


class RiskFlagModel(BaseModel):
    severity: Literal["low", "medium", "high"]
    message: str


class RecommendationFrameModel(BaseModel):
    betterForLowCost: Literal["left", "right", "neutral", "unknown"] = "unknown"
    betterForHigherCover: Literal["left", "right", "neutral", "unknown"] = "unknown"
    betterForTaxEfficiency: Literal["left", "right", "neutral", "unknown"] = "unknown"
    betterForSimplicity: Literal["left", "right", "neutral", "unknown"] = "unknown"
    betterForFlexibility: Literal["left", "right", "neutral", "unknown"] = "unknown"
    betterForImplementationEase: Literal["left", "right", "neutral", "unknown"] = "unknown"


class ScoreReasonModel(BaseModel):
    category: str
    score: float | None = None
    reason: str = ""


class InsuranceComparisonResultModel(BaseModel):
    left: dict[str, Any]
    right: dict[str, Any]
    factsTable: list[FactTableRowModel] = Field(default_factory=list)
    insights: InsightsModel = Field(default_factory=InsightsModel)
    riskFlags: list[RiskFlagModel] = Field(default_factory=list)
    recommendationFrame: RecommendationFrameModel = Field(default_factory=RecommendationFrameModel)
    comparisonMode: Literal["direct", "partial", "scenario"] = "partial"
    narrativeSummary: str = ""
    scoreBreakdown: list[ScoreReasonModel] = Field(default_factory=list)
    weightedTotals: dict[str, float | None] = Field(default_factory=dict)
    scoreExplanation: str = ""
    sourceRefs: dict[str, Any] = Field(default_factory=dict)


class ToolRunListItemModel(BaseModel):
    toolRunId: str
    savedRunId: str
    stepId: str
    toolName: str
    savedRunName: str
    savedAt: str | None = None
    label: str
    hasNormalizedEnvelope: bool = False


class CompareRequestModel(BaseModel):
    clientId: str
    leftToolRunId: str
    rightToolRunId: str
    weights: dict[str, float] | None = None
    factFindVersion: int | str | None = None
    createdBy: str = "advisor"


class SaveComparisonRequestModel(BaseModel):
    clientId: str
    leftToolRunId: str
    rightToolRunId: str
    comparisonType: str = "manual"
    comparisonResult: dict[str, Any]
    factFindVersion: int | str | None = None
    createdBy: str = "advisor"


class SavedComparisonSummaryModel(BaseModel):
    id: str
    clientId: str
    leftToolRunId: str
    rightToolRunId: str
    leftToolName: str
    rightToolName: str
    comparisonMode: str
    createdAt: str | None = None


class ComparisonEnvelopeModel(BaseModel):
    """Optional block stored on each saved step_result."""

    rawOutput: dict[str, Any] | None = None
    normalizedOutput: dict[str, Any] | None = None
    comparisonFacts: list[dict[str, Any]] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    auditTrace: list[dict[str, Any]] = Field(default_factory=list)
