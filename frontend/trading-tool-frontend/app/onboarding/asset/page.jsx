"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function OnboardingAssetRedirectPage() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/onboarding/analysis?onboarding=1&step=analysis");
  }, [router]);

  return null;
}
