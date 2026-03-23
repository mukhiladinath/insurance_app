// =============================================================================
// UTILS — purchaseRetainLifeTPDPolicy
// Pure utility functions. No business rules here.
// =============================================================================

/**
 * Safely parse an ISO 8601 date string.
 * Returns null if the string is absent or produces an invalid Date.
 */
export function safeParseDate(dateStr: string | undefined | null): Date | null {
  if (!dateStr) return null;
  const d = new Date(dateStr);
  return isNaN(d.getTime()) ? null : d;
}

/**
 * Compute age in whole years at a given reference date.
 */
export function computeAge(dateOfBirth: Date, referenceDate: Date): number {
  let age = referenceDate.getFullYear() - dateOfBirth.getFullYear();
  const mDiff = referenceDate.getMonth() - dateOfBirth.getMonth();
  if (mDiff < 0 || (mDiff === 0 && referenceDate.getDate() < dateOfBirth.getDate())) {
    age--;
  }
  return age;
}

/**
 * Compute BMI from height in cm and weight in kg.
 */
export function computeBMI(heightCm: number, weightKg: number): number {
  const heightM = heightCm / 100;
  return round(weightKg / (heightM * heightM), 1);
}

/**
 * Present value of an annuity: PV = PMT × [(1 - (1+r)^-n) / r]
 * Used for TPD income capitalisation.
 *
 * @param annualPayment  Annual income to replace
 * @param years          Number of years (e.g. years to retirement)
 * @param rate           Annual discount rate as a decimal
 */
export function presentValueAnnuity(
  annualPayment: number,
  years: number,
  rate: number,
): number {
  if (years <= 0 || annualPayment <= 0) return 0;
  if (rate === 0) return annualPayment * years;
  return annualPayment * ((1 - Math.pow(1 + rate, -years)) / rate);
}

/**
 * Project a stepped premium forward n years using a constant annual increase factor.
 */
export function projectSteppedPremium(
  currentPremium: number,
  years: number,
  annualIncreaseFactor: number,
): number {
  return round(currentPremium * Math.pow(1 + annualIncreaseFactor, years), 2);
}

/**
 * Clamp a number to the inclusive range [min, max].
 */
export function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

/**
 * Round to a given number of decimal places.
 */
export function round(value: number, decimals: number): number {
  const factor = Math.pow(10, decimals);
  return Math.round(value * factor) / factor;
}

/**
 * Compute a weighted average across a list of (score, weight) pairs.
 * All weights should sum to 1.0.
 */
export function weightedAverage(pairs: Array<{ score: number; weight: number }>): number {
  const totalWeight = pairs.reduce((sum, p) => sum + p.weight, 0);
  if (totalWeight === 0) return 0;
  return round(
    pairs.reduce((sum, p) => sum + p.score * p.weight, 0) / totalWeight,
    2,
  );
}
