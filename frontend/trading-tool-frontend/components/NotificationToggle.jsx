"use client";

import { useState, useEffect } from "react";
import { Bell, BellOff, Loader2 } from "lucide-react";
import { toast } from "react-hot-toast";
import { useTranslation } from "@/app/providers/I18nProvider";
import { useAuth } from "@/components/auth/AuthProvider";
import { API_BASE_URL } from "@/lib/config";

const VAPID_PUBLIC_KEY = process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY;

export default function NotificationToggle({ variant = "default" }) {
  const { user } = useAuth();
  const { locale } = useTranslation();
  const [isSubscribed, setIsSubscribed] = useState(false);
  const [loading, setLoading] = useState(true);
  const [registration, setRegistration] = useState(null);

  useEffect(() => {
    const timer = setTimeout(() => {
      setLoading(false);
    }, 3000);

    if (typeof window !== "undefined" && "serviceWorker" in navigator && "PushManager" in window) {
      navigator.serviceWorker.ready
        .then((reg) => {
          setRegistration(reg);
          return reg.pushManager.getSubscription();
        })
        .then((sub) => {
          setIsSubscribed(!!sub);
          setLoading(false);
          clearTimeout(timer);
        })
        .catch((err) => {
          console.error("SW Ready Error:", err);
          setLoading(false);
          clearTimeout(timer);
        });
    } else {
      setLoading(false);
      clearTimeout(timer);
    }

    return () => clearTimeout(timer);
  }, []);

  const copy = {
    notifications: locale === "nl" ? "Meldingen" : "Notifications",
    loginRequired: locale === "nl" ? "Log in om meldingen in te schakelen" : "Log in to enable notifications",
    notReady: locale === "nl" ? "Meldingen zijn nog niet beschikbaar" : "Notifications are not ready yet",
    permissionDenied: locale === "nl" ? "Toestemming voor meldingen geweigerd" : "Notification permission was denied",
    unavailable: locale === "nl" ? "Pushmeldingen zijn nu niet beschikbaar" : "Push notifications are unavailable right now",
    enabled: locale === "nl" ? "Meldingen ingeschakeld" : "Notifications enabled",
    disabled: locale === "nl" ? "Meldingen uitgeschakeld" : "Notifications disabled",
    enableFailed: locale === "nl" ? "Inschakelen van meldingen mislukte" : "Enabling notifications failed",
    disableFailed: locale === "nl" ? "Uitschakelen van meldingen mislukte" : "Disabling notifications failed",
    pushEnabled: locale === "nl" ? "Push ingeschakeld" : "Push enabled",
    pushDisabled: locale === "nl" ? "Push uitgeschakeld" : "Push disabled",
    pushOn: locale === "nl" ? "Push actief" : "Push on",
    pushOff: locale === "nl" ? "Push uit" : "Push off",
  };

  const urlBase64ToUint8Array = (base64String) => {
    const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
    const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
    const rawData = window.atob(base64);
    const outputArray = new Uint8Array(rawData.length);
    for (let i = 0; i < rawData.length; ++i) {
      outputArray[i] = rawData.charCodeAt(i);
    }
    return outputArray;
  };

  const subscribe = async () => {
    if (!user) {
      toast.error(copy.loginRequired);
      return;
    }
    setLoading(true);
    try {
      if (!registration) {
        toast.error(copy.notReady);
        setLoading(false);
        return;
      }

      const permission = await Notification.requestPermission();
      if (permission !== "granted") {
        toast.error(copy.permissionDenied);
        setLoading(false);
        return;
      }

      if (!VAPID_PUBLIC_KEY) {
        console.error("VAPID_PUBLIC_KEY missing in environment");
        toast.error(copy.unavailable);
        setLoading(false);
        return;
      }

      const subscribeOptions = {
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(VAPID_PUBLIC_KEY),
      };

      const subscription = await registration.pushManager.subscribe(subscribeOptions);
      const p256dh = btoa(String.fromCharCode.apply(null, new Uint8Array(subscription.getKey("p256dh"))));
      const auth = btoa(String.fromCharCode.apply(null, new Uint8Array(subscription.getKey("auth"))));

      const response = await fetch(`${API_BASE_URL}/api/notifications/subscribe`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: user.id || 1,
          subscription: {
            endpoint: subscription.endpoint,
            keys: { p256dh, auth },
          },
        }),
      });

      if (response.ok) {
        setIsSubscribed(true);
        toast.success(copy.enabled);
      } else {
        toast.error(copy.enableFailed);
      }
    } catch (error) {
      console.error("Subscription error:", error);
      toast.error(copy.enableFailed);
    } finally {
      setLoading(false);
    }
  };

  const unsubscribe = async () => {
    setLoading(true);
    try {
      const sub = await registration?.pushManager.getSubscription();
      if (sub) {
        await sub.unsubscribe();
        await fetch(`${API_BASE_URL}/api/notifications/unsubscribe?endpoint=${encodeURIComponent(sub.endpoint)}`, {
          method: "POST",
        });
      }
      setIsSubscribed(false);
      toast.success(copy.disabled);
    } catch (error) {
      console.error("Unsubscribe error:", error);
      toast.error(copy.disableFailed);
    } finally {
      setLoading(false);
    }
  };

  if (variant === "menuItem") {
    return (
      <button
        onClick={isSubscribed ? unsubscribe : subscribe}
        disabled={loading}
        className="w-full flex items-center gap-3 px-4 py-2.5 rounded-lg hover:bg-slate-50 dark:hover:bg-slate-900 transition-all text-secondary dark:text-slate-400 group"
      >
        {loading ? (
          <Loader2 size={16} className="animate-spin text-blue-500" />
        ) : isSubscribed ? (
          <Bell size={16} className="text-blue-500 animate-pulse" />
        ) : (
          <BellOff size={16} />
        )}
        <div className="flex flex-col items-start leading-none">
          <span className="text-[10px] font-black uppercase tracking-widest opacity-40 mb-1">{copy.notifications}</span>
          <span className="font-bold text-[13px] text-foreground dark:text-slate-200">
            {isSubscribed ? copy.pushEnabled : copy.pushDisabled}
          </span>
        </div>
      </button>
    );
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center w-32 h-10 border border-gray-700/50 rounded-lg bg-gray-800/20">
        <Loader2 className="animate-spin text-blue-500" size={18} />
      </div>
    );
  }

  return (
    <button
      onClick={isSubscribed ? unsubscribe : subscribe}
      className={`flex items-center justify-center gap-2 w-32 h-10 rounded-lg transition-all duration-300 border ${
        isSubscribed
          ? "bg-blue-600/10 text-blue-400 border-blue-500/30 hover:bg-blue-600/20 shadow-lg shadow-blue-500/5"
          : "bg-slate-900/50 text-slate-400 border-slate-700/50 hover:text-white hover:bg-slate-800 hover:border-slate-600 shadow-sm"
      }`}
    >
      {isSubscribed ? <Bell size={18} className="animate-pulse" /> : <BellOff size={18} />}
      <span className="text-[10px] font-black uppercase tracking-widest">
        {isSubscribed ? copy.pushOn : copy.pushOff}
      </span>
    </button>
  );
}
