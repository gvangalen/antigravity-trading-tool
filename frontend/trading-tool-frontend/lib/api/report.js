'use client';

import { fetchAuth } from '@/lib/api/auth';

//
// =====================================================
// 🔹 DAILY
// =====================================================
//
export const fetchDailyReportLatest = async (options = {}) =>
  fetchAuth('/api/report/daily/latest', options);

export const fetchDailyReportByDate = async (date, options = {}) =>
  fetchAuth(`/api/report/daily/by-date?date=${encodeURIComponent(date)}`, options);

export const fetchDailyReportDates = async (options = {}) =>
  fetchAuth('/api/report/daily/history', options);

export const generateDailyReport = async () =>
  fetchAuth('/api/report/daily/generate', { method: 'POST' });

export const fetchDailyReportPDF = async (date) =>
  downloadPdf(
    `/api/report/daily/export/pdf?date=${encodeURIComponent(date)}`,
    `daily_report_${date}.pdf`
  );

//
// =====================================================
// 🔹 WEEKLY
// =====================================================
//
export const fetchWeeklyReportLatest = async (options = {}) =>
  fetchAuth('/api/report/weekly/latest', options);

export const fetchWeeklyReportByDate = async (date, options = {}) =>
  fetchAuth(`/api/report/weekly/by-date?date=${encodeURIComponent(date)}`, options);

export const fetchWeeklyReportDates = async (options = {}) =>
  fetchAuth('/api/report/weekly/history', options);

export const generateWeeklyReport = async () =>
  fetchAuth('/api/report/weekly/generate', { method: 'POST' });

export const fetchWeeklyReportPDF = async (date) =>
  downloadPdf(
    `/api/report/weekly/export/pdf?date=${encodeURIComponent(date)}`,
    `weekly_report_${date}.pdf`
  );

//
// =====================================================
// 🔹 MONTHLY
// =====================================================
//
export const fetchMonthlyReportLatest = async (options = {}) =>
  fetchAuth('/api/report/monthly/latest', options);

export const fetchMonthlyReportByDate = async (date, options = {}) =>
  fetchAuth(`/api/report/monthly/by-date?date=${encodeURIComponent(date)}`, options);

export const fetchMonthlyReportDates = async (options = {}) =>
  fetchAuth('/api/report/monthly/history', options);

export const generateMonthlyReport = async () =>
  fetchAuth('/api/report/monthly/generate', { method: 'POST' });

export const fetchMonthlyReportPDF = async (date) =>
  downloadPdf(
    `/api/report/monthly/export/pdf?date=${encodeURIComponent(date)}`,
    `monthly_report_${date}.pdf`
  );

//
// =====================================================
// 🔹 QUARTERLY
// =====================================================
//
export const fetchQuarterlyReportLatest = async (options = {}) =>
  fetchAuth('/api/report/quarterly/latest', options);

export const fetchQuarterlyReportByDate = async (date, options = {}) =>
  fetchAuth(`/api/report/quarterly/by-date?date=${encodeURIComponent(date)}`, options);

export const fetchQuarterlyReportDates = async (options = {}) =>
  fetchAuth('/api/report/quarterly/history', options);

export const generateQuarterlyReport = async () =>
  fetchAuth('/api/report/quarterly/generate', { method: 'POST' });

export const fetchQuarterlyReportPDF = async (date) =>
  downloadPdf(
    `/api/report/quarterly/export/pdf?date=${encodeURIComponent(date)}`,
    `quarterly_report_${date}.pdf`
  );

//
// =====================================================
// 🔁 ASYNC REPORT GENERATION (CELERY SAFE)
// =====================================================
//

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * Start een report task en wacht tot latest beschikbaar is.
 * 404 = report bestaat nog niet → GEEN fout
 */
async function generateAndWait({
  generateFn,
  fetchLatestFn,
  intervalMs = 15000, // 15s
  maxAttempts = 12,   // ±3 minuten
}) {
  // 1️⃣ start celery task
  await generateFn();

  // 2️⃣ poll tot report bestaat
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      const report = await fetchLatestFn();
      return report; // ✅ klaar
    } catch (err) {
      // 404 = task loopt nog
      if (
        err?.status === 404 ||
        err?.message?.includes('404') ||
        err?.detail?.includes('Geen')
      ) {
        await wait(intervalMs);
        continue;
      }

      // ❌ echte fout
      throw err;
    }
  }

  throw new Error('Rapport genereren duurde te lang');
}

//
// =====================================================
// ✅ PUBLIC HELPERS — GEBRUIK DEZE IN DE UI
// =====================================================
//

export const generateWeeklyReportAndWait = async () =>
  generateAndWait({
    generateFn: generateWeeklyReport,
    fetchLatestFn: fetchWeeklyReportLatest,
  });

export const generateMonthlyReportAndWait = async () =>
  generateAndWait({
    generateFn: generateMonthlyReport,
    fetchLatestFn: fetchMonthlyReportLatest,
  });

export const generateQuarterlyReportAndWait = async () =>
  generateAndWait({
    generateFn: generateQuarterlyReport,
    fetchLatestFn: fetchQuarterlyReportLatest,
  });

//
// =====================================================
// 🧾 PDF DOWNLOAD HELPER (BROWSER SAFE)
// =====================================================
//
async function downloadPdf(url, filename) {

  const response = await fetchAuth(url, {
    method: 'GET',
    headers: {
      Accept: 'application/pdf',
    },
    raw: true, // 🔥 cruciaal
  });

  if (!response.ok) {
    console.error('❌ PDF response error', response.status);
    throw new Error(`PDF download mislukt (${response.status})`);
  }

  const blob = await response.blob();
  const blobUrl = window.URL.createObjectURL(blob);

  const link = document.createElement('a');
  link.href = blobUrl;
  link.download = filename;

  document.body.appendChild(link);
  link.click();

  document.body.removeChild(link);
  window.URL.revokeObjectURL(blobUrl);
}
