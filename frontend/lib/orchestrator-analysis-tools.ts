/**
 * Orchestrator tool_ids that perform advisory analysis / recommendations.
 * When a completed run includes any of these, we persist the LLM summary for the client.
 */
export const ANALYSIS_ORCHESTRATOR_TOOL_IDS = new Set<string>([
  'life_insurance_in_super',
  'life_tpd_policy',
  'income_protection_policy',
  'ip_in_super',
  'trauma_critical_illness',
  'tpd_policy_assessment',
  'tpd_in_super',
  'generate_soa',
]);

/** Subset that produces structured JSON comparable in the insurance comparison engine (excludes SOA). */
export const COMPARABLE_INSURANCE_TOOL_IDS = new Set<string>([
  'life_insurance_in_super',
  'life_tpd_policy',
  'income_protection_policy',
  'ip_in_super',
  'trauma_critical_illness',
  'tpd_policy_assessment',
  'tpd_in_super',
]);

export function runIncludesAnalysisTool(
  stepResults: Array<{ tool_id: string; status: string }>,
): boolean {
  return stepResults.some(
    (r) => r.status === 'completed' && ANALYSIS_ORCHESTRATOR_TOOL_IDS.has(r.tool_id),
  );
}
