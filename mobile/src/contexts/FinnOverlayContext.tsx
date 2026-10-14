import { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { Modal } from 'react-native';

import { FinnOverlaySheet } from '../components/assistant/FinnOverlaySheet';
import { useAuth } from '../auth/AuthProvider';
import type { AssistantFeedItem } from '../types/assistant';

type FinnOverlayParams = {
  contextMetric?: string;
  feedItemId?: string;
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
  const { user } = useAuth();
  return <ScopedFinnOverlayProvider accountKey={String(user?.id ?? 'signed-out')}>{children}</ScopedFinnOverlayProvider>;
}

function ScopedFinnOverlayProvider({ children, accountKey }: { children: ReactNode; accountKey: string }) {
  const [isOpen, setIsOpen] = useState(false);
  const [params, setParams] = useState<FinnOverlayParams | null>(null);
  const [draft, setDraft] = useState('');
  const [messages, setMessages] = useState<AssistantFeedItem[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  useEffect(() => {
    setIsOpen(false);
    setParams(null);
    setDraft('');
    setMessages([]);
    setSessionId(null);
  }, [accountKey]);
  const newConversation = useCallback(() => {
    setMessages([]);
    setSessionId(null);
    setDraft('');
  }, []);

  const openFinn = useCallback((next?: FinnOverlayParams) => {
    setParams(next ?? null);
    if (next?.prefill) setDraft(next.prefill);
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
      <Modal
        animationType="fade"
        onRequestClose={closeFinn}
        presentationStyle="overFullScreen"
        statusBarTranslucent={true}
        transparent={true}
        visible={isOpen}
      >
        <FinnOverlaySheet
          prefill={params?.prefill}
          source={params?.source}
          contextMetric={params?.contextMetric}
          feedItemId={params?.feedItemId}
          symbol={params?.symbol}
          onClose={closeFinn}
          query={draft}
          onQueryChange={setDraft}
          messages={messages}
          onMessagesChange={setMessages}
          sessionId={sessionId}
          onSessionIdChange={setSessionId}
          onNewConversation={newConversation}
        />
      </Modal>
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
