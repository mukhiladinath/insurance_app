// =============================================================================
// UTILS — purchaseRetainLifeInsuranceInSuper
// Pure, stateless utility functions. No business rules live here.
// =============================================================================

/**
 * Safely parse an ISO 8601 date string.
 * Returns null if the string is absent or produces an invalid Date.
 */
export function safeParseDate(dateStr: string | undefined | null): Date | null {
  if (!dateStr) return null;
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return null;
  return d;
}

/**
 * Compute the number of whole calendar months between two dates.
 * Returns a positive integer when fromDate is before toDate.
 * A partial month (toDate day < fromDate day) is not counted.
 *
 * @example monthsBetween(new Date('2023-01-15'), new Date('2024-06-10')) === 16
 */
export function monthsBetween(fromDate: Date, toDate: Date): number {
  const yearDiff = toDate.getFullYear() - fromDate.getFullYear();
  const monthDiff = toDate.getMonth() - fromDate.getMonth();
  const total = yearDiff * 12 + monthDiff;
  // Subtract 1 if the day in toDate has not yet reached the day in fromDate
  return toDate.getDate() < fromDate.getDate() ? total - 1 : total;
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
 * Future value of an ordinary annuity (level payments made at end of each period).
 * Represents the compound-growth opportunity cost of paying a recurring premium.
 *
 * FV = P × [((1 + r)^n − 1) / r]
 *
 * @param annualPremium  Annual payment amount in AUD
 * @param years          Number of payment periods (years)
 * @param annualRate     Annual discount/growth rate as a decimal (e.g. 0.07)
 */
export function futureValueAnnuity(
  annualPremium: number,
  years: number,
  annualRate: number,
): number {
  if (years <= 0 || annualPremium <= 0) return 0;
  if (annualRate === 0) return annualPremium * years;
  return annualPremium * ((Math.pow(1 + annualRate, years) - 1) / annualRate);
}

/**
 * Clamp a number to the inclusive range [min, max].
 */
export function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

/**
 * Round a number to a given number of decimal places.
 */
export function round(value: number, decimals: number): number {
  const factor = Math.pow(10, decimals);
  return Math.round(value * factor) / factor;
}
