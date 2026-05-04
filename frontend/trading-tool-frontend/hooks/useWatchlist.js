"use client";

import { useState, useEffect } from "react";
import { fetchWatchlist, addToWatchlist, removeFromWatchlist } from "@/lib/api/watchlist";

export function useWatchlist() {
  const [watchlist, setWatchlist] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadWatchlist();
  }, []);

  async function loadWatchlist() {
    try {
      const data = await fetchWatchlist();
      setWatchlist(data || []);
    } catch (err) {
      console.error("❌ Watchlist load error:", err);
    } finally {
      setLoading(false);
    }
  }

  async function add(symbol) {
    try {
      await addToWatchlist(symbol);
      await loadWatchlist();
    } catch (err) {
      console.error("❌ Watchlist add error:", err);
    }
  }

  async function remove(symbol) {
    try {
      await removeFromWatchlist(symbol);
      await loadWatchlist();
    } catch (err) {
      console.error("❌ Watchlist remove error:", err);
    }
  }

  const isInWatchlist = (symbol) => {
    return (watchlist || []).includes(symbol?.toUpperCase());
  };

  return {
    watchlist,
    loading,
    add,
    remove,
    isInWatchlist,
    refresh: loadWatchlist
  };
}
