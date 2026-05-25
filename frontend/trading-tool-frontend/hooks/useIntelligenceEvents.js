"use client";

import { useState, useRef } from "react";
import { apiGet, apiPost } from "@/lib/api/apiClient";
import { useVisibilityPolling } from "@/hooks/useVisibilityPolling";

export default function useIntelligenceEvents() {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const isFetchingRef = useRef(false);

  const fetchEvents = async (silent = false) => {
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

  useVisibilityPolling(() => fetchEvents(true), {
    intervalMs: 15000,
    backgroundIntervalMs: 60000,
    runImmediately: true,
  });

  return {
    events,
    loading,
    error,
    refresh: fetchEvents,
    archiveEvent,
  };
}
