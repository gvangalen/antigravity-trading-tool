import { createContext, ReactNode, useContext, useMemo, useState } from 'react';

type IntelligenceContextState = {
  asset: string;
  timeframe: string;
  screen?: string;
  page?: string;
  page_type?: string;
};

type IntelligenceContextValue = {
  context: IntelligenceContextState;
  updateContext: (next: Partial<IntelligenceContextState>) => void;
};

const ActiveIntelligenceContext = createContext<IntelligenceContextValue | null>(null);

const DEFAULT_CONTEXT: IntelligenceContextState = {
  asset: 'BTC',
  timeframe: '1D',
  screen: 'Watchlist',
  page: 'Watchlist',
  page_type: 'Watchlist',
};

export function ActiveIntelligenceProvider({ children }: { children: ReactNode }) {
  const [context, setContext] = useState<IntelligenceContextState>(DEFAULT_CONTEXT);

  const value = useMemo<IntelligenceContextValue>(
    () => ({
      context,
      updateContext: (next) => {
        setContext((current) => ({
          ...current,
          ...next,
          page: next.page ?? next.screen ?? current.page,
          page_type: next.page_type ?? next.screen ?? current.page_type,
        }));
      },
    }),
    [context],
  );

  return (
    <ActiveIntelligenceContext.Provider value={value}>
      {children}
    </ActiveIntelligenceContext.Provider>
  );
}

export function useIntelligenceContext() {
  const value = useContext(ActiveIntelligenceContext);
  if (!value) {
    throw new Error('useIntelligenceContext must be used within ActiveIntelligenceProvider');
  }
  return value;
}
