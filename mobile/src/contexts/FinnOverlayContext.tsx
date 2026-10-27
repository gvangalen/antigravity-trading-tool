import { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { Modal } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { FinnOverlaySheet } from '../components/assistant/FinnOverlaySheet';
import { useAuth } from '../auth/AuthProvider';
import type { AssistantFeedItem } from '../types/assistant';
import { assistantApi } from '../services/tradamindApi';

const ACTIVE_FINN_SESSION_ID_KEY = 'active_finn_session_id';

type FinnOverlayParams = {
  contextMetric?: string;
  feedItemId?: string;
  prefill?: string;
  source?: string;
  symbol?: string;
  quoteCurrency?: string | null;
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
  const restoreGeneration = useRef(0);
  useEffect(() => {
    restoreGeneration.current += 1;
    setIsOpen(false);
    setParams(null);
    setDraft('');
    setMessages([]);
    setSessionId(null);
  }, [accountKey]);
  useEffect(() => {
    if (accountKey === 'signed-out') return;
    let canceled = false;
    const generation = ++restoreGeneration.current;
    async function restoreConversation() {
      try {
        const preferences = await assistantApi.preferences();
        const saved = preferences.preferences || {};
        const hasChoice = Object.prototype.hasOwnProperty.call(saved, ACTIVE_FINN_SESSION_ID_KEY);
        const preferred = saved[ACTIVE_FINN_SESSION_ID_KEY];
        if (hasChoice && !preferred) return;
        const conversations = await assistantApi.v2Conversations();
        const id = typeof preferred === 'string' && conversations.some((item) => item.id === preferred)
          ? preferred : conversations[0]?.id;
        if (!id) return;
        const detail = await assistantApi.v2ConversationDetail(id);
        if (canceled || generation !== restoreGeneration.current) return;
        setSessionId(id);
        setMessages((detail.messages || []).filter((item) => item.content?.trim()).map((item, index) => ({
          id: `saved-${index}`,
          type: 'message',
          role: item.role,
          text: item.content,
        })));
      } catch {
        // A temporarily unavailable history must not prevent a new chat.
      }
    }
    void restoreConversation();
    return () => { canceled = true; };
  }, [accountKey]);
  const newConversation = useCallback(() => {
    restoreGeneration.current += 1;
    setMessages([]);
    setSessionId(null);
    setDraft('');
    void assistantApi.updatePreferences({ [ACTIVE_FINN_SESSION_ID_KEY]: null }).catch(() => {});
  }, []);

  const persistSessionId = useCallback((next: string | null | ((current: string | null) => string | null)) => {
    restoreGeneration.current += 1;
    const id = typeof next === 'function' ? next(sessionId) : next;
    setSessionId(id);
    if (id) void assistantApi.updatePreferences({ [ACTIVE_FINN_SESSION_ID_KEY]: id }).catch(() => {});
  }, [sessionId]);

  const openFinn = useCallback((next?: FinnOverlayParams) => {
    restoreGeneration.current += 1;
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
        <SafeAreaProvider>
          <FinnOverlaySheet
            prefill={params?.prefill}
            source={params?.source}
            contextMetric={params?.contextMetric}
            feedItemId={params?.feedItemId}
            symbol={params?.symbol}
            quoteCurrency={params?.quoteCurrency}
            onClose={closeFinn}
            query={draft}
            onQueryChange={setDraft}
            messages={messages}
            onMessagesChange={setMessages}
            sessionId={sessionId}
            onSessionIdChange={persistSessionId}
            onNewConversation={newConversation}
          />
        </SafeAreaProvider>
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
