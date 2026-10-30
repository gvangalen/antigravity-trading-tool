import test from 'node:test';
import assert from 'node:assert/strict';
import { savePdfResponse } from '../lib/api/pdfDownload.mjs';

test('a received PDF remains available to the browser until after download dispatch', async () => {
  const events = [];
  let cleanup;
  const documentRef = {
    body: { appendChild: () => events.push('append') },
    createElement: () => ({
      click: () => events.push('click'),
      remove: () => events.push('remove'),
    }),
  };
  const urlApi = {
    createObjectURL: () => 'blob:report',
    revokeObjectURL: () => events.push('revoke'),
  };
  const response = {
    ok: true,
    blob: async () => new Blob(['%PDF-1.4\nreport data'], { type: 'application/pdf' }),
  };

  const saved = await savePdfResponse(response, 'daily.pdf', {
    documentRef,
    urlApi,
    schedule: (callback, delay) => {
      assert.equal(delay, 60_000);
      cleanup = callback;
    },
  });

  assert.deepEqual(saved, { filename: 'daily.pdf', size: 20 });
  assert.deepEqual(events, ['append', 'click', 'remove']);
  cleanup();
  assert.deepEqual(events, ['append', 'click', 'remove', 'revoke']);
});

test('a non-PDF response is never offered as a download', async () => {
  await assert.rejects(
    savePdfResponse(
      { ok: true, blob: async () => new Blob(['{"error":"unavailable"}']) },
      'daily.pdf',
      { documentRef: {}, urlApi: {} },
    ),
    /not a PDF file/,
  );
});
