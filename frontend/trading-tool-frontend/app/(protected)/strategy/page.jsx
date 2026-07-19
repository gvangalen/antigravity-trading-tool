"use client";

import { useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";

export default function StrategyPage() {
  const router = useRouter();
  const searchParams = useSearchParams();

  useEffect(() => {
    const params = new URLSearchParams(searchParams.toString());
    params.delete("step");
    router.replace(`/setup${params.size ? `?${params.toString()}` : ""}`);
  }, [router, searchParams]);

  return null;
}
