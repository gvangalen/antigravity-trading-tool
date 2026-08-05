"use client";

import { useEffect, useRef, useState } from "react";
import { useAuth } from "@/components/auth/AuthProvider";
import { apiGet, apiPost } from "@/lib/api/apiClient";
import { useVisibilityPolling } from "@/hooks/useVisibilityPolling";

export default function useIntelligenceEvents(options = {}) {
  const { enabled = true, initialDelayMs = 1200 } = options;
  const { user, sessionChecked } = useAuth();
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const isFetchingRef = useRef(false);
  const canFetch = enabled && sessionChecked && !!user;

  const fetchEvents = async (silent = false) => {
    if (!canFetch) return;
    if (isFetchingRef.current) return;
    isFetchingRef.current = true;
    if (!silent) setLoading(true);
    
    try {
      const data = await apiGet("/api/assistant/events", { forceFresh: true });
      setEvents(data || []);
      setError(null);
    } catch (err) {
      if (!err?.message?.includes("401")) {
        console.error("❌ Failed to fetch intelligence events:", err);
      }
      setError("Fout bij ophalen live intelligence");
    } finally {
      setLoading(false);
      isFetchingRef.current = false;
    }
  };

  const archiveEvent = async (eventId) => {
    // Optimistic UI state removal
    setEvents((prev) => prev.filter((ev) => ev.id !== eventId));
    
    try {
      await apiPost(`/api/assistant/events/${eventId}/archive`);
    } catch (err) {
      console.error(`❌ Failed to archive event ${eventId}:`, err);
      // Re-fetch in case of failure to maintain synchronization
      fetchEvents(true);
    }
  };

  useEffect(() => {
    if (canFetch) return;
    setLoading(false);
    setError(null);
    if (!user) {
      setEvents([]);
    }
  }, [canFetch, user]);

  useEffect(() => {
    if (!canFetch) return undefined;

    const timeoutId = setTimeout(() => {
      void fetchEvents(false);
    }, initialDelayMs);

    return () => clearTimeout(timeoutId);
  }, [canFetch, initialDelayMs]);

  useVisibilityPolling(() => fetchEvents(true), {
    enabled: canFetch,
    intervalMs: 60000,
    backgroundIntervalMs: 180000,
    runImmediately: false,
    deps: [user?.id, sessionChecked],
  });

  return {
    events,
    loading,
    error,
    refresh: fetchEvents,
    archiveEvent,
  };
}
