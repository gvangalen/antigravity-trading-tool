export type FinnRunEnvelope = {
  run_id: string;
  conversation_id?: string | null;
  status: string;
  mode?: string | null;
  error_code?: string | null;
  response?: {
    content?: string | null;
    mode?: string | null;
    proposal_id?: string | null;
    confirmation_required?: boolean;
    next_step?: { title?: string; instruction?: string } | null;
  } | null;
};

const TERMINAL = new Set([
  'completed', 'blocked', 'failed', 'canceled', 'unavailable',
  'downgraded', 'rejected', 'clarification_required',
]);

export async function pollFinnRun(
  runId: string,
  readRun: (runId: string) => Promise<FinnRunEnvelope>,
  signal?: AbortSignal,
  maxAttempts = 45,
  delayMs = 1500,
): Promise<FinnRunEnvelope> {
  const deadlineAt = Date.now() + 90000;
  let transientFailures = 0;
  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    if (signal?.aborted) throw new Error('Request canceled');
    if (Date.now() >= deadlineAt) break;
    try {
      const run = await readRun(runId);
      if (run.run_id !== runId) throw new Error('FINN run identity changed');
      transientFailures = 0;
      if (TERMINAL.has(run.status.toLowerCase())) return run;
    } catch (error) {
      const status = (error as { status?: number })?.status;
      if (signal?.aborted || ![0, 502, 503, 504].includes(status ?? -1) || ++transientFailures > 3) throw error;
    }
    if (attempt + 1 < maxAttempts) {
      await new Promise<void>((resolve, reject) => {
        const timer = setTimeout(() => {
          signal?.removeEventListener('abort', onAbort);
          resolve();
        }, delayMs);
        const onAbort = () => {
          clearTimeout(timer);
          reject(new Error('Request canceled'));
        };
        signal?.addEventListener('abort', onAbort, { once: true });
        if (signal?.aborted) onAbort();
      });
    }
  }
  throw new Error('FINN kon dit antwoord niet afronden. Probeer het opnieuw.');
}
