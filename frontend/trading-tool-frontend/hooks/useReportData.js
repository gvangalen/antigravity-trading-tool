'use client';

import { useEffect, useState, useRef } from 'react';
import { waitUntilVisible } from '@/hooks/useVisibilityPolling';
import {
  fetchDailyReportLatest,
  fetchDailyReportByDate,
  fetchDailyReportDates,
  fetchWeeklyReportLatest,
  fetchWeeklyReportByDate,
  fetchWeeklyReportDates,
  fetchMonthlyReportLatest,
  fetchMonthlyReportByDate,
  fetchMonthlyReportDates,
  fetchQuarterlyReportLatest,
  fetchQuarterlyReportByDate,
  fetchQuarterlyReportDates,
} from '@/lib/api/report';

/**
 * ✅ Robuuste report hook — FINAL
 *
 * - Loader stopt ALTIJD zodra report bestaat
 * - Eén expliciete status-machine (geen timing hacks)
 * - Werkt identiek voor daily / weekly / monthly / quarterly
 *
 * status:
 * - idle     → geen report / geen generatie
 * - pending  → Celery bezig (loader zichtbaar)
 * - ready    → report aanwezig (loader UIT)
 * - failed   → timeout / fout
 */
export function useReportData(reportType = 'daily') {
  const [report, setReport] = useState(null);
  const [dates, setDates] = useState([]);
  const [selectedDate, setSelectedDate] = useState('latest');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // 🔑 NIEUW — expliciete status voor loader
  const [status, setStatus] = useState('idle'); // idle | pending | ready | failed

  const isGeneratingRef = useRef(false);
  const pollAttemptsRef = useRef(0);

  const POLL_INTERVAL = 5000; // 5 sec
  const MAX_POLLS = 36;       // 3 min

  const fetchFunctions = {
    daily: {
      getDates: fetchDailyReportDates,
      getLatest: fetchDailyReportLatest,
      getByDate: fetchDailyReportByDate,
    },
    weekly: {
      getDates: fetchWeeklyReportDates,
      getLatest: fetchWeeklyReportLatest,
      getByDate: fetchWeeklyReportByDate,
    },
    monthly: {
      getDates: fetchMonthlyReportDates,
      getLatest: fetchMonthlyReportLatest,
      getByDate: fetchMonthlyReportByDate,
    },
    quarterly: {
      getDates: fetchQuarterlyReportDates,
      getLatest: fetchQuarterlyReportLatest,
      getByDate: fetchQuarterlyReportByDate,
    },
  };

  const current = fetchFunctions[reportType];

  // =====================================================
  // 📆 Datums laden
  // =====================================================
  useEffect(() => {
    let cancelled = false;

    async function loadDates() {
      try {
        const data = await current.getDates();
        if (cancelled) return;

        setDates(
          Array.isArray(data)
            ? data.sort((a, b) => (a < b ? 1 : -1))
            : []
        );
        setSelectedDate('latest');
      } catch {
        setDates([]);
      }
    }

    loadDates();
    return () => {
      cancelled = true;
    };
  }, [reportType]);

  // =====================================================
  // 📄 Rapport laden + polling
  // =====================================================
  useEffect(() => {
    let cancelled = false;

    async function loadReport() {
      setLoading(true);
      setError(null);

      try {
        const fetchOptions = isGeneratingRef.current ? { forceFresh: true } : undefined;
        const data =
          selectedDate === 'latest'
            ? await current.getLatest(fetchOptions)
            : await current.getByDate(selectedDate, fetchOptions);

        if (cancelled) return;

        const reportStatus =
          data && typeof data === 'object' && !Array.isArray(data)
            ? data._status
            : null;

        if (reportStatus === 'pending' || reportStatus === 'pending_first_report') {
          setReport(data);
          setLoading(false);
          setError(null);
          setStatus('idle');
          return;
        }

        // ✅ REPORT BESTAAT → STOP ALLES
        if (data && typeof data === 'object' && Object.keys(data).length > 0) {
          setReport(data);
          isGeneratingRef.current = false;
          pollAttemptsRef.current = 0;
          setLoading(false);
          setStatus('ready'); // 🔑 loader stopt hier
          return;
        }

        throw new Error('empty');
      } catch {
        if (cancelled) return;

        // 🔁 Tijdens generatie blijven pollen
        if (isGeneratingRef.current) {
          pollAttemptsRef.current += 1;

          if (pollAttemptsRef.current >= MAX_POLLS) {
            setError('timeout');
            setLoading(false);
            isGeneratingRef.current = false;
            setStatus('failed');
            return;
          }

          setTimeout(async () => {
            await waitUntilVisible();
            loadReport();
          }, POLL_INTERVAL);
          return;
        }

        // 🧘 Normale situatie: geen report
        setReport(null);
        setError(404);
        setLoading(false);
        setStatus('idle');
      }
    }

    loadReport();
    return () => {
      cancelled = true;
    };
  }, [selectedDate, reportType]);

  // =====================================================
  // 🚀 Start generatie (UI trigger)
  // =====================================================
  const startGenerating = () => {
    isGeneratingRef.current = true;
    pollAttemptsRef.current = 0;
    setLoading(true);
    setError(null);
    setStatus('pending'); // 🔑 loader START
  };

  // =====================================================
  // 🔄 Exposed API
  // =====================================================
  return {
    report,
    dates,
    selectedDate,
    setSelectedDate,

    loading,
    error,
    status,          // 👈 HOOFD-SIGNAAL VOOR LOADER

    hasReport: status === 'ready',
    isGenerating: status === 'pending',

    startGenerating,
  };
}
