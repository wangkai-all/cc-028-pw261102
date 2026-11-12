export function datePart(iso) {
  return iso ? iso.slice(5, 10) : "—";
}

export function fullDate(iso) {
  return iso ? iso.slice(0, 10) : "—";
}

export function timePart(iso) {
  return iso ? iso.slice(11, 16) : "—";
}

export function dateTimePart(iso) {
  if (!iso) return "—";
  return `${iso.slice(5, 10)} ${iso.slice(11, 16)}`;
}

export function weekdayPart(iso) {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const weekday = new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    weekday: "short",
  }).format(date);
  return weekday.replace("星期", "周");
}

export function hours(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
  const n = Number(value);
  if (Number.isInteger(n)) return `${n}h`;
  return `${n.toFixed(digits).replace(/0+$/, "").replace(/\.$/, "")}h`;
}

export function hoursLong(value) {
  if (value === null || value === undefined) return "—";
  const n = Number(value);
  return `${Number.isInteger(n) ? n : n.toFixed(2)} 工作小时`;
}

export function relativeReceived(hoursValue) {
  if (hoursValue === null || hoursValue === undefined) return "";
  if (hoursValue < 24) return `晚到 ${hours(hoursValue, 1)}`;
  return `晚到 ${(hoursValue / 24).toFixed(1)} 天`;
}

export function statusTone(status) {
  return status ? status.toLowerCase().replaceAll("_", "-") : "pending";
}

export function toObservationIso(value) {
  if (!value) return null;
  const withSeconds = value.length === 16 ? `${value}:00` : value;
  return `${withSeconds}+08:00`;
}

export function localObservation(iso) {
  return iso ? iso.slice(0, 16) : "";
}

export function importChangeLabel(change) {
  return {
    CREATED: "首次触发",
    UPDATED: "告警更新",
    CLEARED: "告警解除",
    REOPENED: "重新触发",
  }[change] || change;
}

export function alertTypeLabel(type) {
  return {
    STALLED: "停滞",
    OVERALL_TIMEOUT: "整体超时",
  }[type] || type;
}
