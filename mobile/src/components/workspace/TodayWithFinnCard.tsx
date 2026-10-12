import { useCallback, useEffect, useRef, useState } from 'react';
import { View } from 'react-native';

import { MobileFINNFeed } from '../assistant/MobileFINNFeed';
import { useFinnOverlay } from '../../contexts/FinnOverlayContext';
import { useAppPreferences } from '../../preferences/AppPreferencesProvider';
import { translate } from '../../i18n';
import { coachFeedApi, type MobileCoachFeedItem } from '../../services/tradamindApi';
import { useAuth } from '../../auth/AuthProvider';

// Existing workspace screens keep this component name during their layout
// migration. Their page-specific briefing and queue are no longer rendered.
export type TodayWithFinnQueueItem = {
  key: string;
  label: string;
  value: number | string;
  body: string;
  detail?: string;
};

type TodayWithFinnCardProps = {
  headline: string;
  support: string;
  metaItems?: string[];
  queueItems?: TodayWithFinnQueueItem[];
  queueStatusLabel?: string;
  queueTitle?: string;
  defaultQueueExpanded?: boolean;
};

export function TodayWithFinnCard(_props: TodayWithFinnCardProps) {
  const { language } = useAppPreferences();
  const { user } = useAuth();
  const { openFinn } = useFinnOverlay();
  const [items, setItems] = useState<MobileCoachFeedItem[]>([]);
  const [itemsOwner, setItemsOwner] = useState<number | null>(null);
  const [itemsLanguage, setItemsLanguage] = useState<string | null>(null);
  const [history, setHistory] = useState(false);
  const requestGeneration = useRef(0);
  const currentOwner = useRef(user?.id);
  const currentLanguage = useRef(language);
  currentOwner.current = user?.id;
  currentLanguage.current = language;

  const refresh = useCallback(async () => {
    if (!user?.id) return;
    const owner = user.id;
    const requestedLanguage = language;
    const generation = ++requestGeneration.current;
    try {
      const rows = await coachFeedApi.list(history);
      if (generation === requestGeneration.current && currentOwner.current === owner && currentLanguage.current === requestedLanguage) {
        setItems(rows);
        setItemsOwner(owner);
        setItemsLanguage(requestedLanguage);
      }
    } catch {
      // A failed read leaves the last persisted feed on screen. It never
      // triggers a replacement briefing or a model call.
    }
  }, [history, language, user?.id]);

  useEffect(() => {
    void refresh();
    const timer = setInterval(() => void refresh(), 60_000);
    return () => {
      requestGeneration.current += 1;
      clearInterval(timer);
    };
  }, [refresh]);

  const handleDiscuss = (item: MobileCoachFeedItem) => {
    void coachFeedApi.mark(item.id, 'read').then(refresh).catch(() => {});
    openFinn({
      prefill: translate(language, 'finn.feedDiscussQuery'),
      source: 'coach-feed',
      symbol: item.symbol || undefined,
      feedItemId: item.id,
    });
  };

  const handleArchive = (id: string) => {
    void coachFeedApi.mark(id, 'handled').then(refresh).catch(() => {});
  };

  const scopedItems = itemsOwner === user?.id && itemsLanguage === language ? items : [];
  return (
    <View>
      <MobileFINNFeed
        events={history ? scopedItems : scopedItems.slice(0, 3)}
        history={history}
        language={language}
        onArchive={handleArchive}
        onDiscuss={handleDiscuss}
        onToggleHistory={() => setHistory((value) => !value)}
      />
    </View>
  );
}
