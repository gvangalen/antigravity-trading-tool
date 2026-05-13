import { useCallback, useEffect, useState } from 'react';

import { ApiError } from '../services/apiClient';

type UseApiResourceOptions<T> = {
  fallbackData: T;
  fetcher: () => Promise<T>;
  enabled?: boolean;
};

export function useApiResource<T>({
  enabled = true,
  fallbackData,
  fetcher,
}: UseApiResourceOptions<T>) {
  const [data, setData] = useState<T>(fallbackData);
  const [error, setError] = useState<ApiError | Error | null>(null);
  const [loading, setLoading] = useState(enabled);
  const [refreshing, setRefreshing] = useState(false);
  const [isStale, setIsStale] = useState(false);
  const [updatedAt, setUpdatedAt] = useState<string>(new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));

  const load = useCallback(
    async (mode: 'initial' | 'refresh' = 'refresh') => {
      if (!enabled) return;

      if (mode === 'initial') {
        setLoading(true);
      } else {
        setRefreshing(true);
      }

      try {
        const nextData = await fetcher();
        setData(nextData);
        setError(null);
        setIsStale(false);
        setUpdatedAt(new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));
      } catch (nextError) {
        setError(nextError instanceof Error ? nextError : new Error('Unknown API error'));
        setIsStale(true);
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [enabled, fetcher],
  );

  useEffect(() => {
    load('initial');
  }, [load]);

  return {
    data,
    error,
    isStale,
    loading,
    refresh: () => load('refresh'),
    refreshing,
    updatedAt,
  };
}
