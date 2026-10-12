import { useCallback, useEffect, useState } from 'react';
import { View } from 'react-native';

import { MobileFINNFeed } from '../assistant/MobileFINNFeed';
import { useFinnOverlay } from '../../contexts/FinnOverlayContext';
import { useAppPreferences } from '../../preferences/AppPreferencesProvider';
import { translate } from '../../i18n';
import { coachFeedApi, type MobileCoachFeedItem } from '../../services/tradamindApi';

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
  const { openFinn } = useFinnOverlay();
  const [items, setItems] = useState<MobileCoachFeedItem[]>([]);
  const [history, setHistory] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setItems(await coachFeedApi.list(history));
    } catch {
      // A failed read leaves the last persisted feed on screen. It never
      // triggers a replacement briefing or a model call.
    }
  }, [history, language]);

  useEffect(() => {
    void refresh();
    const timer = setInterval(() => void refresh(), 60_000);
    return () => clearInterval(timer);
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

  return (
    <View>
      <MobileFINNFeed
        events={history ? items : items.slice(0, 3)}
        history={history}
        language={language}
        onArchive={handleArchive}
        onDiscuss={handleDiscuss}
        onToggleHistory={() => setHistory((value) => !value)}
      />
    </View>
  );
}
