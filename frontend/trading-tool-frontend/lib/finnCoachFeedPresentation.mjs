import { parseUtcMoment } from "./report/reportSourceSnapshot.mjs";

export function coachFeedTime(item, locale, copy, now = Date.now()) {
  const value = item?.activity_at || item?.created_at;
  const moment = parseUtcMoment(value);
  if (!moment) return { value: "", label: "—" };

  const dayParts = (date) => {
    const parts = new Intl.DateTimeFormat("en-GB", {
      year: "numeric", month: "2-digit", day: "2-digit",
    }).formatToParts(date);
    const number = (type) => Number(parts.find((part) => part.type === type)?.value);
    return Date.UTC(number("year"), number("month") - 1, number("day"));
  };
  const daysAgo = Math.round((dayParts(new Date(now)) - dayParts(moment)) / 86_400_000);
  const day = daysAgo === 0 ? copy.today : daysAgo === 1 ? copy.yesterday
    : new Intl.DateTimeFormat(locale, { day: "numeric", month: "long" }).format(moment);
  const time = new Intl.DateTimeFormat(locale, {
    hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  }).format(moment);
  return { value: moment.toISOString(), label: `${day} · ${time}` };
}

export function coachFeedPresentation(item, copy) {
  const isPaperBot = item?.event_type === "bot_decision" ||
    (item?.subject_type === "bot" && item?.evidence?.is_live === false);
  const isLiveBot = item?.subject_type === "bot" && item?.evidence?.is_live === true;
  const title = isPaperBot
    ? String(item?.title || "").replace(/\s*[·•]\s*Paper\s*$/i, "")
    : String(item?.title || "");
  let description = String(item?.description || "").trim();
  if (item?.event_type === "bot_decision" &&
      ["hold", "houd_vast"].includes(String(item?.evidence?.action || "").toLowerCase())) {
    const reasons = Array.isArray(item?.evidence?.reasons) ? item.evidence.reasons : [];
    const reason = reasons.find((value) =>
      typeof value === "string" && value.trim());
    description = reason
      ? copy.paperWaitReason.replace("{reason}", reason.trim().replace(/\s+/g, " ").slice(0, 140))
      : copy.noPaperOrder;
  }
  return { title, description, badge: isPaperBot ? "Paper" : isLiveBot ? "Live" : null };
}
