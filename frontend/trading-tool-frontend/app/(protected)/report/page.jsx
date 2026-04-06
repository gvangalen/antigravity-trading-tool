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

// Components
import ReportTabs from '@/components/report/ReportTabs';
import ReportContainer from '@/components/report/layout/ReportContainer';
import ReportLayout from '@/components/report/layout/ReportLayout';
import ReportTerminalHUD from '@/components/report/ReportTerminalHUD';

import ReportGenerateOverlay from '@/components/ui/ReportGenerateOverlay';
import { useModal } from '@/components/modal/ModalProvider';

import {
  Download,
  RefreshCw,
  AlertTriangle,
  Loader2,
  Calendar,
  FileText,
} from 'lucide-react';

/* =====================================================
CONFIG
===================================================== */

const REPORT_TYPES = {
  daily: 'Dag',
  weekly: 'Week',
  monthly: 'Maand',
  quarterly: 'Kwartaal',
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

  const fallbackLabel = REPORT_TYPES[reportType] || 'Rapport';

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
      setError('Er is een fout opgetreden bij het laden van het rapport.');
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
    setGenerateInfo(
      fromAuto
        ? `Nog geen ${fallbackLabel.toLowerCase()}rapport gevonden. Bezig met maken…`
        : `Nieuw ${fallbackLabel.toLowerCase()}rapport wordt gemaakt…`
    );

    try {
      await current.generate();
      await pollUntilNewReport(preferDate);
      showSnackbar(`${fallbackLabel}rapport is gereed`, 'success');
    } catch (err) {
      console.error(err);
      setError('Het maken van het rapport is mislukt.');
    } finally {
      setGenerating(false);
    }
  };

  /* =====================================================
🔥 PDF
===================================================== */

  const handleDownload = async () => {
    if (!report?.report_date) {
      showSnackbar('Rapport nog niet geladen', 'warning');
      return;
    }

    try {
      setPdfLoading(true);

      const date =
        selectedDate === 'latest'
          ? report.report_date
          : selectedDate;

      await current.pdf(date);
      showSnackbar('Download gestart', 'success');

    } catch (err) {
      console.error(err);
      showSnackbar('Fout bij het downloaden van PDF', 'error');
    } finally {
      setPdfLoading(false);
    }
  };

  /* =====================================================
RENDER
===================================================== */

  return (
    <div className="page-container bg-slate-50/50">
      {generating && <ReportGenerateOverlay text={generateInfo} />}

      {/* 🟢 STANDARD PAGE HEADER */}
      <header className="page-header">
        <div className="page-label">
           <FileText size={12} />
           Rapportage
        </div>
        <h1 className="page-title">Rapporten</h1>
        <p className="page-subtitle">Gedetailleerde analyse van handelsdiscipline en resultaten</p>
      </header>

      {/* 📊 OVERZICHT HUD */}
      <ReportTerminalHUD report={report} type={reportType} />

      {/* 🕹️ BEDIENING */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <ReportTabs selected={reportType} onChange={setReportType} />

          <div className="bg-white border border-slate-200 p-1 rounded-xl shadow-sm flex items-center gap-2">
              <div className="flex items-center gap-2 px-3 py-1 border-r border-slate-100">
                  <Calendar size={13} className="text-slate-400" />
                  <select
                      value={selectedDate}
                      onChange={(e) => loadData(e.target.value)}
                      className="bg-transparent text-[11px] font-bold text-slate-600 focus:outline-none appearance-none"
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
                      className="flex items-center gap-2 px-3 py-1.5 hover:bg-slate-50 text-slate-500 hover:text-slate-900 rounded-lg transition-all disabled:opacity-30"
                  >
                      {pdfLoading ? <Loader2 size={13} className="animate-spin" /> : <Download size={13} />}
                      <span className="text-[11px] font-bold uppercase">PDF</span>
                  </button>

                  <button
                      onClick={() => handleGenerate(false, selectedDate)}
                      disabled={generating}
                      className="flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition-all shadow-sm active:scale-95 disabled:bg-slate-300"
                  >
                      <RefreshCw size={13} className={generating ? "animate-spin" : ""} />
                      <span className="text-[11px] font-bold uppercase">Nieuw</span>
                  </button>
              </div>
          </div>
      </div>

      {/* ⚠️ FOUTMELDING */}
      {error && (
        <div className="bg-red-50 border border-red-200 p-6 rounded-2xl flex items-center gap-4 text-red-700">
           <AlertTriangle size={24} />
           <div>
               <div className="text-[11px] font-black uppercase tracking-widest">Foutmelding</div>
               <div className="text-sm font-medium">{error}</div>
           </div>
        </div>
      )}

      {/* 📄 RAPPORT INHOUD */}
      {!loading && report ? (
        <div className="animate-fade-slide">
          <ReportContainer>
            <ReportLayout report={report} />
          </ReportContainer>
        </div>
      ) : (
        loading && (
          <div className="flex flex-col items-center justify-center py-20 animate-pulse">
              <Loader2 size={32} className="animate-spin text-slate-200" />
              <div className="text-[11px] font-bold text-slate-400 uppercase tracking-widest mt-4">Rapport laden...</div>
          </div>
        )
      )}
    </div>
  );
}
