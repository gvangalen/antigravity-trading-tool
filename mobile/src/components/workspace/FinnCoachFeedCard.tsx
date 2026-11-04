import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigation, type NavigationProp } from '@react-navigation/native';
import { View } from 'react-native';

import { MobileFINNFeed } from '../assistant/MobileFINNFeed';
import { useFinnOverlay } from '../../contexts/FinnOverlayContext';
import { useAppPreferences } from '../../preferences/AppPreferencesProvider';
import { translate } from '../../i18n';
import { coachFeedApi, type MobileCoachFeedItem } from '../../services/tradamindApi';
import { useAuth } from '../../auth/AuthProvider';
import type { MainTabParamList } from '../../navigation/MainTabNavigator';

export function FinnCoachFeedCard() {
  const navigation = useNavigation<NavigationProp<MainTabParamList>>();
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
      prefill: `${translate(language, 'finn.feedDiscussQuery')} ${item.evidence?.subject || item.title}`,
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
        onViewReport={(item) => {
          void coachFeedApi.mark(item.id, 'read').then(refresh).catch(() => {});
          navigation.navigate('Report', {
            reportDate: item.evidence?.report_date,
            reportType: item.evidence?.report_type,
          });
        }}
        onToggleHistory={() => setHistory((value) => !value)}
      />
    </View>
  );
}
