"use client";

import { fetchAuth } from "@/lib/api/auth";

//
// =======================================================
// BOT BRAIN MARKET INTELLIGENCE
// =======================================================
//

export const fetchMarketIntelligence = () =>
  fetchAuth(`/api/market/intelligence`, { method: "GET" });
