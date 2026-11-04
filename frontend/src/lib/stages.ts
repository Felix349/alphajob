import type { EventType, Stage } from "@/lib/api/applications";

/** 看板的列：顺序就是求职流程的顺序。 */
export const STAGES: { value: Stage; label: string; dot: string }[] = [
  { value: "wishlist", label: "待投递", dot: "bg-slate-400" },
  { value: "applied", label: "已投递", dot: "bg-sky-500" },
  { value: "written_test", label: "笔试", dot: "bg-violet-500" },
  { value: "interviewing", label: "面试中", dot: "bg-amber-500" },
  { value: "hr", label: "HR 面", dot: "bg-orange-500" },
  { value: "offer", label: "Offer", dot: "bg-emerald-500" },
  { value: "ended", label: "已结束", dot: "bg-zinc-300" },
];

export const STAGE_LABEL = Object.fromEntries(STAGES.map((s) => [s.value, s.label])) as Record<
  Stage,
  string
>;

export const EVENT_TYPES: { value: EventType; label: string; color: string }[] = [
  { value: "interview", label: "面试", color: "#f59e0b" },
  { value: "written_test", label: "笔试", color: "#8b5cf6" },
  { value: "deadline", label: "截止", color: "#ef4444" },
  { value: "other", label: "其他", color: "#64748b" },
];

export const EVENT_TYPE_LABEL = Object.fromEntries(
  EVENT_TYPES.map((t) => [t.value, t.label]),
) as Record<EventType, string>;

export const EVENT_TYPE_COLOR = Object.fromEntries(
  EVENT_TYPES.map((t) => [t.value, t.color]),
) as Record<EventType, string>;
