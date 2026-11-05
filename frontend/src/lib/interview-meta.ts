import type { InterviewStatus, Mastery } from "@/lib/api/interviews";

export const STATUS: Record<InterviewStatus, { label: string; className: string }> = {
  pending: {
    label: "排队中",
    className: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200",
  },
  transcribing: {
    label: "转写中",
    className: "bg-sky-100 text-sky-800 dark:bg-sky-950 dark:text-sky-200",
  },
  analyzing: {
    label: "分析中",
    className: "bg-violet-100 text-violet-800 dark:bg-violet-950 dark:text-violet-200",
  },
  done: {
    label: "已完成",
    className: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200",
  },
  failed: {
    label: "失败",
    className: "bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-200",
  },
};

export const MASTERY: Record<Mastery, string> = {
  new: "待复习",
  reviewing: "复习中",
  mastered: "已掌握",
};

export const SCORE_LABEL: Record<number, string> = {
  1: "没答上",
  2: "较浅",
  3: "基本正确",
  4: "较好",
  5: "很好",
};

export function scoreClass(score: number): string {
  if (score >= 4)
    return "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200";
  if (score === 3) return "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-200";
  return "bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-200";
}

/** 下一场面试的默认轮次：已有 1 场就建议“二面” */
const ROUNDS = ["一面", "二面", "三面", "四面", "HR 面"];
export function suggestRound(existing: number): string {
  return ROUNDS[Math.min(existing, ROUNDS.length - 1)];
}

export function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}
