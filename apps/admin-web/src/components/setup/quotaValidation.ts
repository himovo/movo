export const MAX_SETUP_TOKENS = Number.MAX_SAFE_INTEGER;

export function isValidSetupQuota(value: number | null): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value > 0;
}
