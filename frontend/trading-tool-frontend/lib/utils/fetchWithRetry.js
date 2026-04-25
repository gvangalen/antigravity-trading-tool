// ✅ Universele fetch met retries + foutafhandeling + logging
//    Nu ook mét cookies → credentials: "include"

import { API_BASE_URL } from "../config";

export async function fetchWithRetry(
  endpoint,
  method = "GET",
  body = null,
  retries = 3,
  delay = 2000
) {
  const baseUrl = API_BASE_URL;

  const url = endpoint.startsWith("http")
    ? endpoint
    : `${baseUrl}${endpoint.startsWith("/") ? "" : "/"}${endpoint}`;

  // Kleine waarschuwing als iemand vergeet '/api/' te gebruiken
  if (!endpoint.startsWith("/api/") && !endpoint.startsWith("http")) {
    console.warn(
      `⚠️ Mogelijk fout endpoint zonder '/api/': '${endpoint}' ➝ URL: '${url}'`
    );
  }

  let attempts = 0;

  while (attempts < retries) {
    try {
      const options = {
        method,

        // 🔥 FIX HIER:
        // JWT cookies zoals access_token en refresh_token meesturen!
        credentials: "include",

        headers: {
          "Content-Type": "application/json",
        },
      };

      // Logging voor body
      if (body && ["POST", "PUT", "PATCH"].includes(method.toUpperCase())) {
        options.body = JSON.stringify(body);
        console.log(`🔍 [fetchWithRetry] ${method.toUpperCase()} ${url}`);
        console.log("📦 Body:", body);
      } else {
        console.log(
          `🔍 [fetchWithRetry] ${method.toUpperCase()} ${url} (geen body)`
        );
      }

      // API call
      const response = await fetch(url, options);

      if (!response.ok) {
        const errorText = await response.text();
        const error = new Error(`HTTP ${response.status} - ${errorText}`);
        error.status = response.status;
        error.statusText = response.statusText;
        throw error;
      }

      const data = await response.json();

      if (data === null || data === undefined) {
        throw new Error("❌ Geen data ontvangen");
      }

      return data;
    } catch (err) {
      console.warn(
        `⚠️ Poging ${attempts + 1} mislukt voor ${url}: ${err.message}`
      );
      attempts++;

      if (attempts === retries) throw err;

      await new Promise((res) => setTimeout(res, delay));
    }
  }
}
