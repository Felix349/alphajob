const dateTimeFmt = new Intl.DateTimeFormat("zh-CN", {
  month: "numeric",
  day: "numeric",
  weekday: "short",
  hour: "2-digit",
  minute: "2-digit",
});

const dateFmt = new Intl.DateTimeFormat("zh-CN", { month: "numeric", day: "numeric" });

/** 11/12 周三 14:00 */
export function formatDateTime(iso: string): string {
  return dateTimeFmt.format(new Date(iso));
}

/** 11/12（日期字符串 YYYY-MM-DD 按本地日期解析，避免时区偏移一天） */
export function formatDate(isoDate: string): string {
  const [y, m, d] = isoDate.split("-").map(Number);
  return dateFmt.format(new Date(y, m - 1, d));
}

/** 距离现在多久：今天 / 明天 / 3 天后 */
export function relativeDay(iso: string): string {
  const target = new Date(iso);
  const today = new Date();
  const startOf = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const days = Math.round((startOf(target) - startOf(today)) / 86_400_000);
  if (days === 0) return "今天";
  if (days === 1) return "明天";
  if (days > 1) return `${days} 天后`;
  return `${-days} 天前`;
}

/** <input type="datetime-local"> 的值（本地时间）转成带时区的 ISO 字符串 */
export function localInputToIso(value: string): string {
  return new Date(value).toISOString();
}
