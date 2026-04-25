"use client";

import React, { useState, useEffect } from "react";
import { Bell, BellOff, Loader2 } from "lucide-react";
import { toast } from "react-hot-toast";
import { useAuth } from "@/components/auth/AuthProvider";
import { API_BASE_URL } from "@/lib/config";

const VAPID_PUBLIC_KEY = process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY;

export default function NotificationToggle({ variant = "default" }) {
  const { user } = useAuth();
  const [isSubscribed, setIsSubscribed] = useState(false);
  const [loading, setLoading] = useState(true);
  const [registration, setRegistration] = useState(null);

  useEffect(() => {
    // Veiligheidstimer: Stop sowieso met laden na 3 seconden
    const timer = setTimeout(() => {
      setLoading(prev => {
        if (prev) {
          console.warn("Notification check timed out");
          return false;
        }
        return false;
      });
    }, 3000);

    if (typeof window !== "undefined" && "serviceWorker" in navigator && "PushManager" in window) {
      navigator.serviceWorker.ready.then((reg) => {
        setRegistration(reg);
        reg.pushManager.getSubscription().then((sub) => {
          setIsSubscribed(!!sub);
          setLoading(false);
          clearTimeout(timer);
        });
      }).catch(err => {
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
      toast.error("Log in om notificaties in te schakelen");
      return;
    }
    setLoading(true);
    try {
      if (!registration) {
        toast.error("Service worker niet gereed");
        setLoading(false);
        return;
      }

      const permission = await Notification.requestPermission();
      if (permission !== "granted") {
        toast.error("Notificatie toestemming geweigerd");
        setLoading(false);
        return;
      }

      if (!VAPID_PUBLIC_KEY) {
        console.error("VAPID_PUBLIC_KEY missing in environment");
        toast.error("VAPID Key missing");
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
            keys: { p256dh, auth }
          }
        }),
      });

      if (response.ok) {
        setIsSubscribed(true);
        toast.success("Notificaties actief!");
      }
    } catch (error) {
      console.error("Subscription error:", error);
      toast.error("Fout bij inschakelen");
    } finally {
      setLoading(false);
    }
  };

  const unsubscribe = async () => {
    setLoading(true);
    try {
      const sub = await registration.pushManager.getSubscription();
      if (sub) {
        await sub.unsubscribe();
        await fetch(`${API_BASE_URL}/api/notifications/unsubscribe?endpoint=${encodeURIComponent(sub.endpoint)}`, {
          method: "POST",
        });
      }
      setIsSubscribed(false);
      toast.success("Notificaties uit");
    } catch (error) {
      console.error("Unsubscribe error:", error);
      toast.error("Fout bij uitschakelen");
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
          <span className="text-[10px] font-black uppercase tracking-widest opacity-40 mb-1">Notificaties</span>
          <span className="font-bold text-[13px] text-foreground dark:text-slate-200">
            {isSubscribed ? "Push Ingeschakeld" : "Push Uitgeschakeld"}
          </span>
        </div>
      </button>
    );
  }

  if (loading) return (
    <div className="flex items-center justify-center w-32 h-10 border border-gray-700/50 rounded-lg bg-gray-800/20">
      <Loader2 className="animate-spin text-blue-500" size={18} />
    </div>
  );

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
        {isSubscribed ? "Push Actief" : "Push Uit"}
      </span>
    </button>
  );
}

