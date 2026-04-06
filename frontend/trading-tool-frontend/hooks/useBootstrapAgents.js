"use client";

import { useState } from "react";
import { bootstrapAgents } from "@/lib/api/systemApi";

export default function useBootstrapAgents() {

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const runBootstrap = async () => {

    setLoading(true);
    setError(null);

    try {

      const res = await bootstrapAgents();
      return res;

    } catch (err) {

      console.error("Bootstrap agents error:", err);
      setError(err?.message || "Bootstrap agents mislukt");

    } finally {

      setLoading(false);

    }

  };

  return {
    runBootstrap,
    loading,
    error,
  };
}
