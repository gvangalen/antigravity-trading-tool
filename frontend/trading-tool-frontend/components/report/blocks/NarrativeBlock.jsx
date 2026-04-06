'use client';

import ReportSection from "../ReportSection";

/* =====================================================
   HELPERS — robuuste normalisatie
   (nodig i.v.m. variabele AI-output)
===================================================== */

function normalizeText(input) {
  if (input === null || input === undefined) return null;

  if (typeof input === "string") {
    const t = input.trim();
    return t.length > 0 ? t : null;
  }

  if (typeof input === "number" || typeof input === "boolean") {
    return String(input);
  }

  if (Array.isArray(input)) {
    const lines = input
      .map((v) => normalizeText(v))
      .filter(Boolean);

    return lines.length ? lines.join("\n\n") : null;
  }

  if (typeof input === "object") {
    // Veelvoorkomende AI-structuren
    if (input.text) return normalizeText(input.text);
    if (input.summary) return normalizeText(input.summary);
    if (input.description) return normalizeText(input.description);
    if (input.content) return normalizeText(input.content);

    if (input.bullets) return normalizeText(input.bullets);
    if (input.points) return normalizeText(input.points);
    if (input.items) return normalizeText(input.items);

    // ❗ Alleen in development JSON dumpen
    if (process.env.NODE_ENV === "development") {
      try {
        const s = JSON.stringify(input, null, 2);
        return s && s.trim().length ? s : null;
      } catch {
        return null;
      }
    }

    return null;
  }

  return null;
}

/* =====================================================
   Resolver — expliciet > field > niets
===================================================== */

function resolveText({ text, field, report }) {
  const direct = normalizeText(text);
  if (direct) return direct;

  if (field && report && typeof report === "object") {
    return normalizeText(report[field]);
  }

  return null;
}

/* =====================================================
   NarrativeBlock — DOCUMENT STYLE
   ✔ géén card
   ✔ géén border
   ✔ verhaal / analyse
===================================================== */

export default function NarrativeBlock({
  title,
  text,
  field,
  report,
}) {
  const content = resolveText({ text, field, report });
  if (!content) return null;

  const paragraphs = content
    .split(/\n\s*\n/)
    .map((p) => p.trim())
    .filter(Boolean);

  return (
    <ReportSection title={title}>
      <div className="space-y-6 text-[16px] leading-[1.8] text-slate-700 font-medium tracking-tight">
        {paragraphs.map((p, i) => (
          <p key={i} className="animate-in fade-in slide-in-from-left-2 duration-500">{p}</p>
        ))}
      </div>
    </ReportSection>
  );
}
