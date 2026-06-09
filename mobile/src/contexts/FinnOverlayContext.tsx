import { createContext, ReactNode, useCallback, useContext, useMemo, useState } from 'react';

import { FinnScreen } from '../screens/FinnScreen';

type FinnOverlayParams = {
  contextMetric?: string;
  prefill?: string;
  source?: string;
  symbol?: string;
};

type FinnOverlayValue = {
  closeFinn: () => void;
  isOpen: boolean;
  openFinn: (params?: FinnOverlayParams) => void;
  params: FinnOverlayParams | null;
};

const FinnOverlayContext = createContext<FinnOverlayValue | null>(null);

export function FinnOverlayProvider({ children }: { children: ReactNode }) {
  const [isOpen, setIsOpen] = useState(false);
  const [params, setParams] = useState<FinnOverlayParams | null>(null);

  const openFinn = useCallback((next?: FinnOverlayParams) => {
    setParams(next ?? null);
    setIsOpen(true);
  }, []);

  const closeFinn = useCallback(() => {
    setIsOpen(false);
    setParams(null);
  }, []);

  const value = useMemo<FinnOverlayValue>(
    () => ({ closeFinn, isOpen, openFinn, params }),
    [closeFinn, isOpen, openFinn, params],
  );

  return (
    <FinnOverlayContext.Provider value={value}>
      {children}
      {isOpen ? (
        <FinnScreen
          isOverlay={true}
          prefill={params?.prefill}
          source={params?.source}
          contextMetric={params?.contextMetric}
          symbol={params?.symbol}
          onClose={closeFinn}
        />
      ) : null}
    </FinnOverlayContext.Provider>
  );
}

export function useFinnOverlay() {
  const value = useContext(FinnOverlayContext);
  if (!value) {
    throw new Error('useFinnOverlay must be used within FinnOverlayProvider');
  }
  return value;
}
