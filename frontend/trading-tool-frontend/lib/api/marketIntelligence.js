"use client";

import { fetchAuth } from "@/lib/api/auth";

//
// =======================================================
// BOT BRAIN MARKET INTELLIGENCE
// =======================================================
//

export const fetchMarketIntelligence = (symbol = "BTC") =>
  fetchAuth(`/api/market/intelligence?symbol=${symbol}`, { method: "GET" });
