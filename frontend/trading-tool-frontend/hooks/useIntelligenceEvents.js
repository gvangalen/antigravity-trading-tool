"use client";

import { useState, useEffect, useRef } from "react";
import { apiGet, apiPost } from "@/lib/api/apiClient";

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
      const data = await apiGet("/api/assistant/events");
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
    fetchEvents();

    // Poll for real-time events every 15 seconds to keep the Terminal feel
    const interval = setInterval(() => {
      fetchEvents(true);
    }, 15000);

    return () => clearInterval(interval);
  }, []);

  return {
    events,
    loading,
    error,
    refresh: fetchEvents,
    archiveEvent,
  };
}
