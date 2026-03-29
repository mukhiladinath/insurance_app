/**
 * Detect when the user asked the AI bar to compare insurance analyses.
 * Used after a multi-tool run to auto-open the Compare tab with results.
 */
const COMPARE_PATTERN =
  /\b(compare|comparison|versus|vs\.?|side[\s-]by[\s-]side|which\s+is\s+better|difference\s+between)\b/i;

export function instructionSuggestsInsuranceCompare(instruction: string): boolean {
  return COMPARE_PATTERN.test(instruction.trim());
}
