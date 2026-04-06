'use client';

import CardWrapper from "@/components/ui/CardWrapper";

export default function NotificationCard({ icon, title, subtitle }) {
  return (
    <CardWrapper>
      <div
        className="
          p-5 rounded-xl
          bg-[var(--card-bg)]
          border border-[var(--card-border)]
          shadow-sm
          transition hover:shadow-md hover:-translate-y-[1px]
        "
      >
        {/* Header */}
        <div className="flex items-center gap-2 mb-2">
          <div className="p-2 rounded-lg bg-[var(--bg-soft)] text-[var(--text-dark)] shadow-sm">
            {icon}
          </div>

          <h2 className="text-sm font-semibold text-[var(--text-dark)]">
            {title}
          </h2>
        </div>

        {/* Subtext */}
        <p className="text-sm text-[var(--text-light)] leading-relaxed">
          {subtitle}
        </p>
      </div>
    </CardWrapper>
  );
}
