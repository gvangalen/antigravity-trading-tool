type SetupRecord = Record<string, unknown>;

function isRecord(value: unknown): value is SetupRecord {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

export function extractOwnedActiveSetup(source: unknown): SetupRecord | undefined {
  const record = Array.isArray(source)
    ? source.find(isRecord)
    : isRecord(source) ? source : undefined;
  if (!record) return undefined;

  // /setups/active returns a status wrapper even when no owned setup exists.
  // Never turn that wrapper into a synthetic plan named after the current asset.
  if ('active' in record) {
    return isRecord(record.active) ? record.active : undefined;
  }

  return typeof record.id === 'number' || typeof record.setup_id === 'number'
    ? record : undefined;
}
