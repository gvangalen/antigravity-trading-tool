'use client';

import { useState, useEffect, useMemo, useRef } from 'react';
import {
  fetchDailyReportLatest,
  fetchDailyReportByDate,
  fetchDailyReportDates,
  generateDailyReport,
  fetchDailyReportPDF,
  fetchWeeklyReportLatest,
  fetchWeeklyReportByDate,
  fetchWeeklyReportDates,
  generateWeeklyReport,
  fetchWeeklyReportPDF,
  fetchMonthlyReportLatest,
  fetchMonthlyReportByDate,
  fetchMonthlyReportDates,
  generateMonthlyReport,
  fetchMonthlyReportPDF,
  fetchQuarterlyReportLatest,
  fetchQuarterlyReportByDate,
  fetchQuarterlyReportDates,
  generateQuarterlyReport,
  fetchQuarterlyReportPDF,
} from '@/lib/api/report';
import { assistantChat } from '@/lib/api/ai';

// Components
import ReportTabs from '@/components/report/ReportTabs';
import ReportContainer from '@/components/report/layout/ReportContainer';
import ReportLayout from '@/components/report/layout/ReportLayout';
import ReportTerminalHUD from '@/components/report/ReportTerminalHUD';
import { ReportSkeleton } from '@/components/dashboard/DashboardSkeleton';
import DashboardErrorBoundary from '@/components/ui/DashboardErrorBoundary';

import ReportGenerateOverlay from '@/components/ui/ReportGenerateOverlay';
import { useModal } from '@/components/modal/ModalProvider';

import {
  Download,
  RefreshCw,
  AlertTriangle,
  Loader2,
  Calendar,
  FileText,
  Brain,
  ShieldCheck,
  ClipboardList,
  ChevronDown,
} from 'lucide-react';

/* =====================================================
CONFIG
===================================================== */

const REPORT_TYPES = {
  daily: 'Daily',
  weekly: 'Weekly',
  monthly: 'Monthly',
  quarterly: 'Quarterly',
};

const AUTO_GENERATE_IF_EMPTY = true;
const POLL_INTERVAL_MS = 4000;
const POLL_MAX_ATTEMPTS = 60;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/* =====================================================
HELPERS
===================================================== */

function sortDatesDesc(list) {
  if (!Array.isArray(list)) return [];
  return [...list].sort((a, b) => (a < b ? 1 : -1));
}

function getReportSignature(report) {
  if (!report) return '';
  return (
    report.generated_at ||
    report.updated_at ||
    report.created_at ||
    JSON.stringify(report)
  );
}

function getNested(obj, path, fallback = null) {
  return path.split('.').reduce((acc, key) => acc?.[key], obj) ?? fallback;
}

function getFinnReportSummary(report) {
  const text = report?.response || '';
  if (!text) {
    return 'Finn analyseerde je recente interacties, risicochecks en beslisflows.';
  }

  const cleaned = text
    .replace(/^dit is een finn operator-\/disciplinerapport, los van je dagelijkse trading report\.\s*/i, '')
    .replace(/\s+/g, ' ')
    .trim();

  if (!cleaned) {
    return 'Finn analyseerde je recente interacties, risicochecks en beslisflows.';
  }

  return cleaned.length > 220 ? `${cleaned.slice(0, 220).trim()}...` : cleaned;
}

function formatFinnReportSource(report) {
  const source = getNested(report, 'state.source.primary') || getNested(report, 'state.analysis.source.primary');
  return source || 'Finn auditdata';
}

function FinnReportsPanel() {
  const [finnReport, setFinnReport] = useState(null);
  const [finnLoading, setFinnLoading] = useState(true);
  const [finnError, setFinnError] = useState('');
  const [expanded, setExpanded] = useState(false);

  const loadFinnReport = async () => {
    setFinnLoading(true);
    setFinnError('');

    try {
      const data = await assistantChat(
        'Geef mijn Finn rapport van vandaag',
        {
          page: '/report',
          page_type: 'Reports',
          report_family: 'finn_reports',
        },
        []
      );
      setFinnReport(data || null);
    } catch (err) {
      console.error('Finn report load failed:', err);
      setFinnError('Finn rapport kon niet geladen worden.');
    } finally {
      setFinnLoading(false);
    }
  };

  useEffect(() => {
    loadFinnReport();
  }, []);

  const analysis = finnReport?.state?.analysis || finnReport?.analysis || {};
  const metrics = analysis?.metrics || {};
  const source = formatFinnReportSource(finnReport);
  const summary = getFinnReportSummary(finnReport);
  const reportType = finnReport?.state?.report_type || analysis?.report_type || 'finn_reflection_report';
  const separateFrom = finnReport?.state?.separate_from || analysis?.separate_from || 'daily_trading_report';
  const isContractValid = finnReport?.intent === 'finn_report' && finnReport?.flow === 'finn_report';

  const metricItems = [
    ['Acties', metrics.actions_today ?? metrics.actions_7d ?? metrics.actions_30d],
    ['Afgeremd', metrics.plan_deviation_events_today ?? metrics.plan_deviation_events_7d ?? metrics.plan_deviation_events_30d],
    ['Skips', metrics.skipped_today ?? metrics.skipped_7d ?? metrics.skipped_30d],
  ].filter(([, value]) => value !== undefined && value !== null);

  return (
    <section className="my-10 md:my-12">
      <div className="flex items-center gap-2 mb-4">
        <Brain size={14} className="text-blue-600 dark:text-blue-400" />
        <span className="text-[11px] font-black uppercase tracking-[0.28em] text-slate-400 dark:text-slate-500">
          Finn Reports
        </span>
      </div>

      <div className="rounded-[2rem] border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950 shadow-xl shadow-blue-900/5 overflow-hidden">
        <div className="p-6 md:p-8 border-b border-slate-100 dark:border-slate-800/80">
          <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-5">
            <div className="max-w-3xl">
              <h2 className="text-2xl md:text-3xl font-black tracking-tight text-slate-950 dark:text-slate-100">
                Persoonlijke Finn rapportage
              </h2>
              <p className="mt-3 text-sm md:text-[15px] leading-relaxed text-slate-500 dark:text-slate-400 max-w-2xl">
                Read-only rapporten over je Finn-activiteit, risicochecks en beslisflows.
                Los van trading reports. Dit rapport analyseert je gebruik van Finn, niet de markt.
              </p>
            </div>

            <div className="flex flex-wrap gap-2">
              {['READ-ONLY', 'AUDITDATA', 'LOS VAN TRADING REPORTS'].map((label) => (
                <span
                  key={label}
                  className="px-3 py-1.5 rounded-full bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-[10px] font-black uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400"
                >
                  {label}
                </span>
              ))}
            </div>
          </div>
        </div>

        <div className="p-6 md:p-8">
          {finnLoading ? (
            <div className="flex items-center gap-3 text-sm font-bold text-slate-500 dark:text-slate-400">
              <Loader2 size={16} className="animate-spin text-blue-600" />
              Finn rapport ophalen...
            </div>
          ) : finnError ? (
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 rounded-2xl border border-red-200 dark:border-red-900/40 bg-red-50 dark:bg-red-950/20 p-4">
              <div className="flex items-center gap-3 text-sm font-bold text-red-700 dark:text-red-300">
                <AlertTriangle size={16} />
                {finnError}
              </div>
              <button
                onClick={loadFinnReport}
                className="self-start sm:self-auto px-4 py-2 rounded-xl bg-white dark:bg-slate-950 border border-red-200 dark:border-red-900/40 text-[10px] font-black uppercase tracking-widest text-red-700 dark:text-red-300 hover:bg-red-100 dark:hover:bg-red-950/40 transition-colors"
              >
                Opnieuw
              </button>
            </div>
          ) : (
            <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-50/60 dark:bg-slate-900/40 p-5 md:p-6">
              <div className="flex flex-col xl:flex-row xl:items-start xl:justify-between gap-5">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2 mb-3">
                    <span className="inline-flex items-center gap-1.5 text-[10px] font-black uppercase tracking-[0.18em] text-blue-600 dark:text-blue-400">
                      <ClipboardList size={13} />
                      Laatste Finn report
                    </span>
                    <span className="px-2.5 py-1 rounded-full bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-[9px] font-black uppercase tracking-[0.14em] text-slate-500 dark:text-slate-400">
                      Gebruikersactiviteit
                    </span>
                    <span className="px-2.5 py-1 rounded-full bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-900/40 text-[9px] font-black uppercase tracking-[0.14em] text-emerald-700 dark:text-emerald-300">
                      Auditdata
                    </span>
                  </div>

                  <p className="text-sm md:text-[15px] leading-relaxed text-slate-700 dark:text-slate-300 max-w-3xl">
                    {summary}
                  </p>

                  <div className="mt-5 grid grid-cols-1 sm:grid-cols-3 gap-3 max-w-2xl">
                    {(metricItems.length ? metricItems : [['Bron', source], ['Type', reportType], ['Scheiding', separateFrom]]).map(([label, value]) => (
                      <div
                        key={label}
                        className="rounded-xl bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-800 p-3"
                      >
                        <div className="text-[9px] font-black uppercase tracking-[0.16em] text-slate-400 dark:text-slate-500">
                          {label}
                        </div>
                        <div className="mt-1 text-sm font-black text-slate-900 dark:text-slate-100 truncate">
                          {String(value)}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="flex flex-col gap-2 sm:flex-row xl:flex-col xl:min-w-[180px]">
                  <button
                    onClick={() => setExpanded((value) => !value)}
                    className="inline-flex items-center justify-center gap-2 rounded-xl bg-slate-950 dark:bg-blue-600 px-5 py-3 text-[11px] font-black uppercase tracking-widest text-white hover:bg-blue-700 dark:hover:bg-blue-500 transition-all active:scale-[0.98]"
                  >
                    Lees Finn rapport
                    <ChevronDown
                      size={14}
                      className={`transition-transform ${expanded ? 'rotate-180' : ''}`}
                    />
                  </button>
                  <button
                    onClick={loadFinnReport}
                    className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950 px-5 py-3 text-[11px] font-black uppercase tracking-widest text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-900 transition-all active:scale-[0.98]"
                  >
                    <RefreshCw size={13} />
                    Vernieuw
                  </button>
                </div>
              </div>

              {expanded && (
                <div className="mt-6 border-t border-slate-200 dark:border-slate-800 pt-5">
                  <div className="flex flex-wrap items-center gap-2 mb-4">
                    <span className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[10px] font-black uppercase tracking-[0.14em] border ${
                      isContractValid
                        ? 'bg-emerald-50 dark:bg-emerald-950/30 border-emerald-200 dark:border-emerald-900/40 text-emerald-700 dark:text-emerald-300'
                        : 'bg-amber-50 dark:bg-amber-950/30 border-amber-200 dark:border-amber-900/40 text-amber-700 dark:text-amber-300'
                    }`}>
                      <ShieldCheck size={12} />
                      {isContractValid ? 'Contract OK' : 'Contract controleren'}
                    </span>
                    <span className="text-[10px] font-black uppercase tracking-[0.16em] text-slate-400 dark:text-slate-500">
                      Bron: {source}
                    </span>
                  </div>
                  <div className="rounded-xl bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-800 p-4">
                    <p className="whitespace-pre-wrap text-sm leading-7 text-slate-700 dark:text-slate-300">
                      {finnReport?.response || 'Geen rapporttekst beschikbaar.'}
                    </p>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

/* =====================================================
PAGE
==================================================== */

export default function ReportPage() {
  const { showSnackbar } = useModal();

  const [reportType, setReportType] = useState('daily');
  const [report, setReport] = useState(null);
  const [dates, setDates] = useState([]);
  const [selectedDate, setSelectedDate] = useState('latest');

  const [loading, setLoading] = useState(true);
  const [pdfLoading, setPdfLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [generateInfo, setGenerateInfo] = useState('');
  const [error, setError] = useState('');

  const pollTokenRef = useRef(0);
  const lastSignatureRef = useRef('');

  const fallbackLabel = REPORT_TYPES[reportType] || 'Report';

  const reportFns = useMemo(
    () => ({
      daily: {
        getLatest: fetchDailyReportLatest,
        getByDate: fetchDailyReportByDate,
        getDates: fetchDailyReportDates,
        generate: generateDailyReport,
        pdf: fetchDailyReportPDF,
      },
      weekly: {
        getLatest: fetchWeeklyReportLatest,
        getByDate: fetchWeeklyReportByDate,
        getDates: fetchWeeklyReportDates,
        generate: generateWeeklyReport,
        pdf: fetchWeeklyReportPDF,
      },
      monthly: {
        getLatest: fetchMonthlyReportLatest,
        getByDate: fetchMonthlyReportByDate,
        getDates: fetchMonthlyReportDates,
        generate: generateMonthlyReport,
        pdf: fetchMonthlyReportPDF,
      },
      quarterly: {
        getLatest: fetchQuarterlyReportLatest,
        getByDate: fetchQuarterlyReportByDate,
        getDates: fetchQuarterlyReportDates,
        generate: generateQuarterlyReport,
        pdf: fetchQuarterlyReportPDF,
      },
    }),
    []
  );

  const current = reportFns[reportType];

  /* =====================================================
LOAD
===================================================== */

  const loadData = async (date = 'latest') => {
    setLoading(true);
    setError('');
    setSelectedDate(date);

    try {
      const rawDates = await current.getDates();
      setDates(sortDatesDesc(rawDates || []));

      const data =
        date === 'latest'
          ? await current.getLatest()
          : await current.getByDate(date);

      if (!data && AUTO_GENERATE_IF_EMPTY) {
        setLoading(false);
        handleGenerate(true, date);
        return;
      }

      setReport(data || null);
      lastSignatureRef.current = getReportSignature(data);
    } catch {
      setError('An error occurred while loading the report.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData('latest');
  }, [reportType]);

  /* =====================================================
GENERATE
===================================================== */

  const pollUntilNewReport = async (preferDate = 'latest') => {
    pollTokenRef.current += 1;
    const token = pollTokenRef.current;

    let attempts = 0;

    while (attempts < POLL_MAX_ATTEMPTS) {
      if (pollTokenRef.current !== token) return;

      await sleep(POLL_INTERVAL_MS);

      const data =
        preferDate === 'latest'
          ? await current.getLatest()
          : await current.getByDate(preferDate);

      const sig = getReportSignature(data);

      if (sig && sig !== lastSignatureRef.current) {
        lastSignatureRef.current = sig;
        setReport(data);
        return;
      }

      attempts++;
    }

    throw new Error('Polling timeout');
  };

  const handleGenerate = async (fromAuto = false, preferDate = 'latest') => {
    setGenerating(true);
    setLoading(true); // 🔥 Toon skeleton achter de overlay
    setGenerateInfo(
      fromAuto
        ? `No ${fallbackLabel.toLowerCase()} report found. Creating…`
        : `Generating new ${fallbackLabel.toLowerCase()} report…`
    );

    try {
      await current.generate();
      await pollUntilNewReport(preferDate);
      showSnackbar(`${fallbackLabel} report is ready`, 'success');
    } catch (err) {
      console.error(err);
      setError('Failed to generate report.');
    } finally {
      setGenerating(false);
      setLoading(false);
    }
  };

  /* =====================================================
🔥 PDF
===================================================== */

  const handleDownload = async () => {
    if (!report?.report_date) {
      showSnackbar('Report not yet loaded', 'warning');
      return;
    }

    try {
      setPdfLoading(true);

      const date =
        selectedDate === 'latest'
          ? report.report_date
          : selectedDate;

      await current.pdf(date);
      showSnackbar('Download started', 'success');

    } catch (err) {
      console.error(err);
      showSnackbar('Error downloading PDF', 'error');
    } finally {
      setPdfLoading(false);
    }
  };

  /* =====================================================
RENDER
===================================================== */

  return (
    <div className="page-container bg-white dark:bg-[#020617] transition-colors min-h-screen">
      {generating && <ReportGenerateOverlay text={generateInfo} />}

      {/* 🟢 STANDARD PAGE HEADER */}
      <header className="page-header border-l-4 border-blue-600 pl-8 mb-16">
        <div className="page-label text-[11px] font-black text-blue-600 dark:text-blue-500 uppercase tracking-[0.3em] mb-2 opacity-80 flex items-center gap-2">
           <FileText size={12} />
           Tradamind Intelligence
        </div>
        <h1 className="page-title text-5xl font-black text-slate-900 dark:text-slate-100 tracking-tight leading-none mb-4">Tradamind Reports</h1>
        <div className="flex flex-col sm:flex-row sm:items-center gap-3 sm:gap-4">
          <p className="page-subtitle text-[15px] font-medium text-slate-400 dark:text-slate-500 max-w-2xl leading-relaxed">
            Detailed analysis of trading discipline and results
          </p>
          <div className="hidden sm:block h-4 w-[1px] bg-slate-200 dark:bg-slate-800" />
          <div className="flex items-center gap-1.5">
            <div className="w-1.5 h-1.5 rounded-full bg-blue-500" />
            <span className="text-[10px] font-black text-blue-600 dark:text-blue-400 uppercase tracking-[0.15em] opacity-80">
              Generated by Tradamind AI
            </span>
          </div>
        </div>
      </header>

      {/* 📊 OVERVIEW HUD */}
      <DashboardErrorBoundary>
        <ReportTerminalHUD report={report} type={reportType} loading={loading} />
      </DashboardErrorBoundary>

      {/* 🕹️ CONTROLS */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 py-8">
          <ReportTabs selected={reportType} onChange={setReportType} />

          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 p-1 rounded-xl shadow-sm flex items-center gap-2 transition-colors">
              <div className="flex items-center gap-2 px-3 py-1 border-r border-slate-100 dark:border-slate-800">
                  <Calendar size={13} className="text-slate-400 dark:text-slate-500" />
                  <select
                      value={selectedDate}
                      onChange={(e) => loadData(e.target.value)}
                      className="bg-transparent text-[11px] font-bold text-slate-600 dark:text-slate-400 focus:outline-none appearance-none"
                  >
                      <option value="latest">Recent</option>
                      {dates.map((d) => (
                          <option key={d} value={d}>{d}</option>
                      ))}
                  </select>
              </div>

              <div className="flex items-center gap-2 pr-1">
                  <button
                      onClick={handleDownload}
                      disabled={pdfLoading || !report}
                      className="flex items-center gap-2 px-3 py-1.5 hover:bg-slate-50 dark:hover:bg-slate-800 text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white rounded-lg transition-all disabled:opacity-30"
                  >
                      {pdfLoading ? <Loader2 size={13} className="animate-spin" /> : <Download size={13} />}
                      <span className="text-[11px] font-black uppercase tracking-widest">PDF</span>
                  </button>

                  <button
                      onClick={() => handleGenerate(false, selectedDate)}
                      disabled={generating}
                      className="flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition-all shadow-lg shadow-blue-600/10 active:scale-95 disabled:bg-slate-300"
                  >
                      <RefreshCw size={13} className={generating ? "animate-spin" : ""} />
                      <span className="text-[11px] font-black uppercase tracking-widest">New</span>
                  </button>
              </div>
          </div>
      </div>

      {/* ⚠️ ERROR MESSAGE */}
      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-900/30 p-6 rounded-2xl flex items-center gap-4 text-red-700 dark:text-red-300 shadow-sm transition-colors">
           <AlertTriangle size={24} />
           <div>
               <div className="text-[11px] font-black uppercase tracking-widest">Error Message</div>
               <div className="text-sm font-medium">{error}</div>
           </div>
        </div>
      )}

      <DashboardErrorBoundary>
        <FinnReportsPanel />
      </DashboardErrorBoundary>

      {/* 📄 REPORT CONTENT */}
      {loading ? (
        <div className="pt-8">
          <ReportSkeleton />
        </div>
      ) : (
        report && (
          <div className="animate-fade-slide pb-24">
            <DashboardErrorBoundary>
              <ReportContainer>
                <ReportLayout report={report} />
              </ReportContainer>
            </DashboardErrorBoundary>
          </div>
        )
      )}
    </div>
  );
}
