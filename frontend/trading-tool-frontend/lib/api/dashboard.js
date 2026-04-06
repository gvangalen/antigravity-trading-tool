'use client';

import { fetchAuth } from "@/lib/api/auth";
import { API_BASE_URL } from '@/lib/config';

// ============================================================
// 📊 1) Dashboard hoofddata
// ============================================================
export const fetchDashboardData = async () =>
  fetchAuth(`/api/dashboard`, { method: 'GET' });

// ============================================================
// ❤️ 2) Gezondheidscheck (mag zonder auth, maar werkt ook prima met cookies)
// ============================================================
export const fetchHealthCheck = async () =>
  fetchAuth(`/api/health`, { method: 'GET' });

// ============================================================
// 🤖 3) AI Trading Advies
// ============================================================
export const fetchTradingAdvice = async (symbol = 'BTC') =>
  fetchAuth(`/api/ai/trading/trading_advice?symbol=${symbol}`, {
    method: 'GET',
  });

// ============================================================
// 🏆 4) Top Setups
// ============================================================
export const fetchTopSetups = async () =>
  fetchAuth(`/api/top_setups`, { method: 'GET' });

// ============================================================
// 🧪 5) Test route (developer only)
// ============================================================
export const testDashboardAPI = async () =>
  fetchAuth(`/api/dashboard/test`, { method: 'GET' });
