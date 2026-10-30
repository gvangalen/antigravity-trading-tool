export async function savePdfResponse(
  response,
  filename,
  { documentRef = document, urlApi = URL, schedule = setTimeout } = {},
) {
  if (!response?.ok || typeof response.blob !== 'function') {
    throw new Error('PDF response is unavailable');
  }

  const blob = await response.blob();
  if ((await blob.slice(0, 5).text()) !== '%PDF-') {
    throw new Error('PDF response is not a PDF file');
  }

  const blobUrl = urlApi.createObjectURL(blob);
  const link = documentRef.createElement('a');
  link.href = blobUrl;
  link.download = filename;

  try {
    documentRef.body.appendChild(link);
    link.click();
  } finally {
    link.remove();
    // Browsers may resolve the download only after the click task completes.
    schedule(() => urlApi.revokeObjectURL(blobUrl), 60_000);
  }

  return { filename, size: blob.size };
}
