'use client';

import * as React from 'react';
import * as RadixTooltip from '@radix-ui/react-tooltip';
import { Info } from 'lucide-react';

export default function InfoTooltip({ text }) {
  return (
    <RadixTooltip.Provider delayDuration={150}>
      <RadixTooltip.Root>
        {/* Trigger Icon */}
        <RadixTooltip.Trigger asChild>
          <button
            type="button"
            className="
              inline-flex items-center justify-center
              ml-1 
              text-[var(--icon-muted)]
              hover:text-[var(--primary)]
              transition-colors
            "
          >
            <Info className="w-4 h-4" />
          </button>
        </RadixTooltip.Trigger>

        {/* Tooltip */}
        <RadixTooltip.Portal>
          <RadixTooltip.Content
            sideOffset={6}
            className="
              z-50 max-w-xs
              rounded-md
              px-3 py-2
              text-sm leading-snug
              bg-[var(--surface-1)]
              text-[var(--text-dark)]
              border border-[var(--border)]
              shadow-lg
              dark:bg-[var(--surface-2)]
              dark:text-[var(--text-light)]
              dark:border-gray-700
              animate-fade-slide
            "
          >
            {text}

            <RadixTooltip.Arrow
              className="fill-[var(--surface-1)] dark:fill-[var(--surface-2)]"
            />
          </RadixTooltip.Content>
        </RadixTooltip.Portal>
      </RadixTooltip.Root>
    </RadixTooltip.Provider>
  );
}
