"use client";

import { Clock, Loader2, RefreshCw, Sparkles } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Progress } from "@/components/ui/progress";
import { useGeneratePlan, usePlan, useTogglePlanItem } from "@/hooks/use-agent";
import type { PlanKind, TodayPlanData, WeekPlanData } from "@/lib/api/agent";
import { cn } from "@/lib/utils";

const WEEKDAY = "日一二三四五六";

export function PlanCard() {
  const [kind, setKind] = useState<PlanKind>("today");
  const { data: plan, isPending } = usePlan(kind);
  const generate = useGeneratePlan(kind);

  function run() {
    generate.mutate(undefined, { onError: (e) => toast.error(e.message) });
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-3">
        <div role="radiogroup" aria-label="计划类型" className="flex gap-1 rounded-lg bg-muted p-1">
          {(["today", "week"] as const).map((k) => (
            <button
              key={k}
              type="button"
              role="radio"
              aria-checked={kind === k}
              onClick={() => setKind(k)}
              className={cn(
                "rounded-md px-3 py-1 text-sm transition-colors",
                kind === k
                  ? "bg-background shadow-xs"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {k === "today" ? "今日计划" : "本周计划"}
            </button>
          ))}
        </div>
        {plan && (
          <Button size="sm" variant="ghost" onClick={run} disabled={generate.isPending}>
            <RefreshCw className={cn("size-3.5", generate.isPending && "animate-spin")} />
            重新生成
          </Button>
        )}
      </CardHeader>
      <CardContent className="text-sm">
        {isPending && <p className="text-muted-foreground">加载中…</p>}
        {!isPending && !plan && (
          <div className="flex flex-col items-center gap-3 py-8 text-center">
            <p className="text-muted-foreground">
              {kind === "today"
                ? "根据你的面试日程、备考进度和薄弱点，排出今天最该做的事。"
                : "排好本周的面试节点，并倒推每天该准备什么。"}
            </p>
            <Button onClick={run} disabled={generate.isPending}>
              {generate.isPending ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Sparkles className="size-4" />
              )}
              {generate.isPending
                ? "生成中…（约 15 秒）"
                : kind === "today"
                  ? "生成今日计划"
                  : "生成本周计划"}
            </Button>
          </div>
        )}
        {plan && kind === "today" && (
          <TodayView planId={plan.id} data={plan.plan as TodayPlanData} done={plan.done_items} />
        )}
        {plan && kind === "week" && <WeekView data={plan.plan as WeekPlanData} />}
        {plan && (
          <p className="mt-4 text-xs text-muted-foreground">
            生成于 {new Date(plan.created_at).toLocaleString("zh-CN")}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function TodayView({
  planId,
  data,
  done,
}: {
  planId: string;
  data: TodayPlanData;
  done: number[];
}) {
  const toggle = useTogglePlanItem();
  const total = data.items.reduce((s, i) => s + i.minutes, 0);

  return (
    <div className="flex flex-col gap-4">
      <div className="rounded-lg bg-muted/50 p-3">
        <p className="font-medium">{data.focus}</p>
        <div className="mt-2 flex items-center gap-2 text-xs text-muted-foreground">
          <Progress
            value={(done.length / Math.max(data.items.length, 1)) * 100}
            className="h-1.5 flex-1"
          />
          {done.length}/{data.items.length} · 共约 {Math.round((total / 60) * 10) / 10} 小时
        </div>
      </div>
      <ol className="flex flex-col gap-2">
        {data.items.map((item, i) => {
          const isDone = done.includes(i);
          return (
            <li key={i} className="flex items-start gap-3 rounded-lg border p-3">
              <Checkbox
                className="mt-0.5"
                checked={isDone}
                aria-label={item.title}
                onCheckedChange={(c) =>
                  toggle.mutate(
                    { planId, index: i, done: Boolean(c) },
                    { onError: (e) => toast.error(e.message) },
                  )
                }
              />
              <div className="min-w-0 flex-1">
                <div className="flex items-start justify-between gap-2">
                  <p className={cn("font-medium", isDone && "text-muted-foreground line-through")}>
                    {item.priority === 1 && !isDone && (
                      <span className="mr-1 text-rose-600">●</span>
                    )}
                    {item.title}
                  </p>
                  <span className="flex shrink-0 items-center gap-1 text-xs text-muted-foreground">
                    <Clock className="size-3" />
                    {item.minutes} 分钟
                  </span>
                </div>
                <p className="mt-1 text-xs text-muted-foreground">{item.reason}</p>
                {item.application_id && (
                  <Link
                    href={`/applications/${item.application_id}`}
                    className="mt-1 inline-block text-xs underline-offset-4 hover:underline"
                  >
                    查看相关投递 →
                  </Link>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function WeekView({ data }: { data: WeekPlanData }) {
  const today = new Date().toLocaleDateString("sv-SE");
  return (
    <div className="flex flex-col gap-4">
      <p className="rounded-lg bg-muted/50 p-3 font-medium">{data.overview}</p>
      {data.key_dates.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {data.key_dates.map((d, i) => (
            <span
              key={i}
              className="rounded-md bg-amber-100 px-2 py-0.5 text-xs text-amber-900 dark:bg-amber-950 dark:text-amber-100"
            >
              {d}
            </span>
          ))}
        </div>
      )}
      <ol className="flex flex-col gap-1">
        {data.days.map((day) => {
          const d = new Date(`${day.date}T00:00:00`);
          const isToday = day.date === today;
          return (
            <li
              key={day.date}
              className={cn(
                "grid grid-cols-[4.5rem_1fr] gap-3 rounded-lg p-2",
                isToday && "bg-primary/5 ring-1 ring-primary/20",
              )}
            >
              <div className="text-xs">
                <div className={cn("font-medium", isToday && "text-primary")}>
                  周{WEEKDAY[d.getDay()]}
                  {isToday && " · 今天"}
                </div>
                <div className="text-muted-foreground">
                  {d.getMonth() + 1}/{d.getDate()}
                </div>
              </div>
              <div>
                <p className="font-medium">{day.focus}</p>
                {day.tasks.length > 0 && (
                  <ul className="mt-0.5 list-disc pl-4 text-xs text-muted-foreground">
                    {day.tasks.map((t, i) => (
                      <li key={i}>{t}</li>
                    ))}
                  </ul>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
