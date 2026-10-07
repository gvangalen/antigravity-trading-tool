export async function logoutSession({ fetchImpl, logoutUrl, meUrl, headers, refreshToken, verifyBrowser }) {
  const response = await fetchImpl(logoutUrl, {
    method: "POST",
    credentials: "include",
    headers,
    body: refreshToken ? JSON.stringify({ refresh_token: refreshToken }) : undefined,
  });
  if (!response.ok) return { success: false };

  if (verifyBrowser) {
    const check = await fetchImpl(meUrl, {
      method: "GET",
      credentials: "include",
      cache: "no-store",
      headers: { "Cache-Control": "no-store" },
    });
    if (check.status !== 401) return { success: false };
  }

  return { success: true };
}
