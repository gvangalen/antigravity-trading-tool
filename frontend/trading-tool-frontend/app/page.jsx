"use client";

import Image from "next/image";
import Link from "next/link";
import {
  ArrowRight,
  Check,
  MessageCircle,
  ShieldCheck,
  Activity,
} from "lucide-react";
import { useAuth } from "@/components/auth/AuthProvider";
import { useTranslation } from "@/app/providers/I18nProvider";

function ActionLink({ href, children, light = false }) {
  return (
    <Link
      href={href}
      className={`inline-flex min-h-12 items-center justify-center gap-3 rounded-full px-6 text-sm font-semibold transition-colors ${
        light
          ? "border border-slate-300 bg-white text-slate-900 hover:border-blue-500 hover:text-blue-700"
          : "bg-blue-600 text-white hover:bg-blue-700"
      }`}
    >
      {children}
      <ArrowRight size={17} aria-hidden="true" />
    </Link>
  );
}

export default function LandingPage() {
  const { isAuthenticated } = useAuth();
  const { t } = useTranslation();
  const c = t.publicPages.landing;
  const destination = isAuthenticated ? "/asset" : "/login";
  const action = isAuthenticated ? c.openDashboard : c.startTrial;
  const steps = [
    [MessageCircle, c.step1Title, c.step1Body],
    [Activity, c.step2Title, c.step2Body],
    [ShieldCheck, c.step3Title, c.step3Body],
  ];
  const plans = [
    { name: "Basis", price: 89, tagline: c.pricing.basicTagline, features: c.pricing.basicFeatures },
    { name: "Pro", price: 149, tagline: c.pricing.proTagline, features: c.pricing.proFeatures, featured: true },
  ];

  return (
    <div className="min-h-screen bg-white text-slate-950">
      <header className="relative z-20 border-b border-slate-200/80 bg-white">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-5 sm:h-20 sm:px-8">
          <Link href="/" className="flex items-center gap-3" aria-label={c.brandHome}>
            <Image src="/tradamind_icon_v2.png" alt="" width={38} height={38} className="rounded-md" />
            <span className="text-lg font-bold">Tradamind</span>
          </Link>
          <nav className="hidden items-center gap-8 md:flex" aria-label={c.siteNavigation}>
            <a href="#hoe-het-werkt" className="text-sm font-medium text-slate-600 hover:text-blue-700">{c.seeHow}</a>
            <a href="#prijzen" className="text-sm font-medium text-slate-600 hover:text-blue-700">{c.pricingEyebrow}</a>
          </nav>
          <div className="flex items-center gap-4">
            {!isAuthenticated && <Link href="/login" className="hidden text-sm font-semibold text-slate-700 hover:text-blue-700 sm:block">{c.login}</Link>}
            <Link href={destination} className="inline-flex min-h-10 items-center gap-2 rounded-full bg-slate-950 px-5 text-sm font-semibold text-white hover:bg-blue-700">
              {action}<ArrowRight size={16} aria-hidden="true" />
            </Link>
          </div>
        </div>
      </header>

      <main>
        <section className="relative isolate overflow-hidden bg-[#f3f8f8]">
          <Image
            src="/dashboard_real_preview.png"
            alt=""
            fill
            priority
            sizes="100vw"
            className="object-cover object-center opacity-[0.12]"
          />
          <div className="absolute inset-0 bg-white/70" aria-hidden="true" />
          <div className="relative mx-auto max-w-7xl px-5 pb-14 pt-16 sm:px-8 sm:pb-16 sm:pt-20 lg:pt-24">
            <div className="max-w-[900px]">
              <p className="mb-5 flex items-center gap-3 text-sm font-semibold text-blue-700">
                <span className="h-2 w-2 rounded-full bg-emerald-500" />{c.heroEyebrow}
              </p>
              <h1 className="max-w-[880px] text-5xl font-semibold leading-[1.04] text-slate-950 sm:text-6xl lg:text-7xl">
                {c.heroTitle}
              </h1>
              <p className="mt-7 max-w-2xl text-lg leading-relaxed text-slate-700 sm:text-xl">{c.heroBody}</p>
              <div className="mt-9 flex flex-col gap-3 sm:flex-row">
                <ActionLink href={destination}>{action}</ActionLink>
                <ActionLink href="#hoe-het-werkt" light>{c.seeHow}</ActionLink>
              </div>
              <p className="mt-5 text-sm text-slate-600">{c.heroFootnote}</p>
            </div>
          </div>
          <div className="relative border-t border-slate-200/80 bg-white/75">
            <div className="mx-auto grid max-w-7xl gap-0 px-5 sm:grid-cols-3 sm:px-8">
              {[c.heroPoint1, c.heroPoint2, c.heroPoint3].map((point, index) => (
                <div key={point} className="flex items-center gap-3 border-b border-slate-200 py-4 text-sm font-medium text-slate-700 last:border-b-0 sm:border-b-0 sm:border-r sm:px-6 sm:first:pl-0 sm:last:border-r-0">
                  <span className="text-xs font-bold text-blue-600">0{index + 1}</span>{point}
                </div>
              ))}
            </div>
          </div>
        </section>

        <section id="hoe-het-werkt" className="py-20 sm:py-28">
          <div className="mx-auto max-w-7xl px-5 sm:px-8">
            <div className="grid gap-6 lg:grid-cols-[1fr_1fr] lg:gap-16">
              <div>
                <p className="text-sm font-semibold text-blue-700">{c.workflowEyebrow}</p>
                <h2 className="mt-4 max-w-xl text-4xl font-semibold leading-tight sm:text-5xl">{c.workflowTitle}</h2>
              </div>
              <p className="max-w-xl self-end text-lg leading-relaxed text-slate-600">{c.workflowBody}</p>
            </div>
            <div className="mt-14 grid gap-8 border-t border-slate-200 pt-9 md:grid-cols-3 md:gap-12">
              {steps.map(([Icon, title, body], index) => (
                <div key={title}>
                  <div className="flex items-center justify-between text-blue-700"><Icon size={23} strokeWidth={1.7} aria-hidden="true" /><span className="text-sm font-semibold">0{index + 1}</span></div>
                  <h3 className="mt-7 text-xl font-semibold">{title}</h3>
                  <p className="mt-3 text-sm leading-relaxed text-slate-600">{body}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="bg-[#edf5f3] py-20 sm:py-28">
          <div className="mx-auto grid max-w-7xl gap-12 px-5 sm:px-8 lg:grid-cols-[0.9fr_1.1fr] lg:items-center lg:gap-20">
            <div>
              <p className="text-sm font-semibold text-blue-700">{c.exampleEyebrow}</p>
              <h2 className="mt-4 text-4xl font-semibold leading-tight sm:text-5xl">{c.exampleTitle}</h2>
              <p className="mt-6 text-lg leading-relaxed text-slate-700">{c.exampleBody}</p>
              <p className="mt-6 text-xs leading-relaxed text-slate-500">{c.exampleDisclaimer}</p>
            </div>
            <div className="border-l-2 border-blue-600 pl-6 sm:pl-9">
              <div className="flex items-center gap-3"><span className="flex h-9 w-9 items-center justify-center rounded-full bg-blue-600 font-bold text-white">F</span><span className="font-semibold">Finn</span><span className="ml-auto text-xs text-slate-500">{c.exampleLabel}</span></div>
              <p className="mt-8 text-sm text-slate-600">{c.examplePrompt}</p>
              <blockquote className="mt-5 text-2xl font-medium leading-snug text-slate-950 sm:text-3xl">“{c.exampleResponse}”</blockquote>
              <p className="mt-5 leading-relaxed text-slate-700">{c.exampleDetail}</p>
              <p className="mt-7 flex items-center gap-2 text-sm font-semibold text-emerald-800"><ShieldCheck size={18} aria-hidden="true" />{c.exampleGuardrail}</p>
            </div>
          </div>
        </section>

        <section className="py-20 sm:py-28">
          <div className="mx-auto max-w-7xl px-5 sm:px-8">
            <p className="text-sm font-semibold text-blue-700">{c.platformEyebrow}</p>
            <h2 className="mt-4 max-w-3xl text-4xl font-semibold leading-tight sm:text-5xl">{c.platformTitle}</h2>
            <div className="mt-12 grid gap-8 border-t border-slate-200 pt-8 md:grid-cols-2 md:gap-16">
              <div><Activity size={23} className="text-blue-700" aria-hidden="true" /><h3 className="mt-5 text-xl font-semibold">{c.dashboardTitle}</h3><p className="mt-3 max-w-md text-sm leading-relaxed text-slate-600">{c.dashboardBody}</p></div>
              <div><ShieldCheck size={23} className="text-emerald-700" aria-hidden="true" /><h3 className="mt-5 text-xl font-semibold">{c.botTitle}</h3><p className="mt-3 max-w-md text-sm leading-relaxed text-slate-600">{c.botBody}</p></div>
            </div>
          </div>
        </section>

        <section id="prijzen" className="bg-slate-50 py-20 sm:py-28">
          <div className="mx-auto max-w-7xl px-5 sm:px-8">
            <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
              <div><p className="text-sm font-semibold text-blue-700">{c.pricingEyebrow}</p><h2 className="mt-4 text-4xl font-semibold sm:text-5xl">{c.pricingTitle}</h2></div>
              <p className="max-w-sm text-sm text-slate-600">{c.pricingSubtitle}</p>
            </div>
            <div className="mt-12 grid gap-10 border-t border-slate-300 pt-10 md:grid-cols-2 md:gap-16">
              {plans.map((plan) => (
                <div key={plan.name} className="flex flex-col md:border-r md:border-slate-200 md:pr-12 md:last:border-r-0 md:last:pr-0">
                  <div className="flex items-start justify-between gap-3">
                    <div>{plan.featured && <p className="mb-2 text-xs font-semibold text-blue-700">{c.pricing.featuredBadge}</p>}<h3 className="text-2xl font-semibold">{plan.name}</h3><p className="mt-2 text-sm text-slate-600">{plan.tagline}</p></div>
                    <p className="whitespace-nowrap text-3xl font-semibold">€{plan.price}<span className="text-sm font-normal text-slate-500"> / {c.pricePeriod}</span></p>
                  </div>
                  <ul className="mt-8 flex-1 space-y-3">{plan.features.map(feature => <li key={feature} className="flex gap-3 text-sm text-slate-700"><Check size={17} className="shrink-0 text-emerald-700" aria-hidden="true" />{feature}</li>)}</ul>
                  <div className="mt-9"><ActionLink href={destination} light={!plan.featured}>{action}</ActionLink></div>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="border-t border-slate-200 bg-white py-20 sm:py-28">
          <div className="mx-auto flex max-w-7xl flex-col gap-8 px-5 sm:px-8 md:flex-row md:items-end md:justify-between">
            <div><p className="text-sm font-semibold text-blue-700">{c.heroEyebrow}</p><h2 className="mt-4 max-w-2xl text-4xl font-semibold leading-tight sm:text-5xl">{c.finalTitle}</h2><p className="mt-4 max-w-xl text-slate-600">{c.finalBody}</p></div>
            <ActionLink href={destination}>{action}</ActionLink>
          </div>
        </section>
      </main>
      <footer className="border-t border-slate-200 px-5 py-8 text-center text-xs text-slate-500">{c.footer.rights}</footer>
    </div>
  );
}
