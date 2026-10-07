import { normalizeDcaWeekday } from "../setup/dcaWeekday.mjs";

export function formatDcaSchedule(setup, copy = {}) {
  if (String(setup?.setup_type || setup?.type || "").toLowerCase() !== "dca") return "";
  const frequency = String(setup?.dca_frequency || "").toLowerCase();
  if (frequency === "daily") return copy.scheduleDaily || "Daily";
  if (frequency === "weekly") {
    const weekday = normalizeDcaWeekday(setup?.dca_day);
    const label = copy.scheduleWeekdays?.[weekday];
    return label ? (copy.scheduleWeekly || "Every {day}").replace("{day}", label) : "";
  }
  if (frequency === "monthly") {
    const day = Number(setup?.dca_month_day);
    return Number.isInteger(day) && day >= 1 && day <= 28
      ? (copy.scheduleMonthly || "Monthly on day {day}").replace("{day}", String(day))
      : "";
  }
  return "";
}
