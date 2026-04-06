'use client';

import Link from 'next/link';
import CardWrapper from '@/components/ui/CardWrapper';
import { useSidebarData } from '@/hooks/useSidebarData';
import { CalendarDays, TrendingUp, Bot } from 'lucide-react';

export default function RightSidebarCard() {
  const { summary, trades, aiStatus, loading } = useSidebarData();

  return (
    <CardWrapper>
      <div className="space-y-6">

        {/* ================================
           📅 Dagelijks Rapport
        ================================= */}
        <div
          className="
            p-5 rounded-xl 
            border border-[var(--card-border)]
            bg-[var(--card-bg)]
            shadow-sm 
            hover:shadow-md hover:-translate-y-[1px]
            transition-all
          "
        >
          {/* Icon + Titel */}
          <div className="flex items-center gap-3 mb-3">
            <div className="p-2 rounded-lg bg-blue-100 dark:bg-blue-900 shadow-sm">
              <CalendarDays className="w-5 h-5 text-blue-600 dark:text-blue-300" />
            </div>
            <h3 className="text-sm font-semibold text-[var(--text-dark)]">
              Dagelijks Rapport
            </h3>
          </div>

          {/* Content */}
          {loading ? (
            <p className="text-sm text-[var(--text-light)] italic">Laden...</p>
          ) : (
            <div className="text-sm text-[var(--text-dark)] leading-relaxed">
              <p className="mb-2">
                {summary || 'Geen samenvatting beschikbaar.'}
              </p>

              <Link
                href="/report"
                className="text-[var(--primary-dark)] hover:underline text-xs"
              >
                Bekijk volledig rapport →
              </Link>
            </div>
          )}
        </div>

        {/* ================================
           📈 Actieve Trades
        ================================= */}
        <div
          className="
            p-5 rounded-xl 
            border border-[var(--card-border)]
            bg-[var(--card-bg)]
            shadow-sm 
            hover:shadow-md hover:-translate-y-[1px]
            transition-all
          "
        >
          {/* Icon + Titel */}
          <div className="flex items-center gap-3 mb-3">
            <div className="p-2 rounded-lg bg-green-100 dark:bg-green-900 shadow-sm">
              <TrendingUp className="w-5 h-5 text-green-600 dark:text-green-300" />
            </div>
            <h3 className="text-sm font-semibold text-[var(--text-dark)]">
              Actieve Trades
            </h3>
          </div>

          {/* Content */}
          {loading ? (
            <p className="text-sm text-[var(--text-light)] italic">Laden...</p>
          ) : trades.length > 0 ? (
            <ul className="text-sm space-y-2 text-[var(--text-dark)]">
              {trades.map((trade) => (
                <li key={trade.id} className="flex justify-between">
                  <span>{trade.symbol}</span>
                  <span className="font-medium">{trade.status}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-[var(--text-light)] italic">
              Geen actieve trades.
            </p>
          )}
        </div>

        {/* ================================
           🤖 AI Trading Bot
        ================================= */}
        <div
          className="
            p-5 rounded-xl 
            border border-[var(--card-border)]
            bg-[var(--card-bg)]
            shadow-sm 
            hover:shadow-md hover:-translate-y-[1px]
            transition-all
          "
        >
          {/* Icon + Titel */}
          <div className="flex items-center gap-3 mb-3">
            <div className="p-2 rounded-lg bg-purple-100 dark:bg-purple-900 shadow-sm">
              <Bot className="w-5 h-5 text-purple-600 dark:text-purple-300" />
            </div>
            <h3 className="text-sm font-semibold text-[var(--text-dark)]">
              AI Trading Bot
            </h3>
          </div>

          {/* Content */}
          {loading ? (
            <p className="text-sm text-[var(--text-light)] italic">Botstatus ophalen...</p>
          ) : (
            <div className="text-sm text-[var(--text-dark)] leading-relaxed">
              <p><strong>Status:</strong> {aiStatus.state || 'onbekend'}</p>
              <p><strong>Strategie:</strong> {aiStatus.strategy || 'n.v.t.'}</p>
              <p><strong>Laatste update:</strong> {aiStatus.updated || 'onbekend'}</p>
            </div>
          )}
        </div>

      </div>
    </CardWrapper>
  );
}
