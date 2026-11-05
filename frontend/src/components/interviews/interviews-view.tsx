"use client";

import Link from "next/link";
import { useMemo } from "react";

import { InterviewRow } from "@/components/interviews/interview-row";
import { Skeleton } from "@/components/ui/skeleton";
import { useApplications } from "@/hooks/use-applications";
import { useAllInterviews } from "@/hooks/use-interviews";

export function InterviewsView() {
  const { data: interviews, isPending, error } = useAllInterviews();
  const { data: apps } = useApplications();
  const appName = useMemo(
    () => new Map((apps ?? []).map((a) => [a.id, `${a.company} · ${a.role}`])),
    [apps],
  );

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <div className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">面试复盘</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            在投递详情页里新建复盘。所有被问过的题目会汇总到
            <Link href="/questions" className="mx-1 font-medium underline">
              题库
            </Link>
            里。
          </p>
        </div>
      </div>
      {isPending && <Skeleton className="h-48 w-full rounded-xl" />}
      {error && <p className="text-sm text-destructive">加载失败：{error.message}</p>}
      {interviews && interviews.length === 0 && (
        <div className="rounded-xl border border-dashed p-12 text-center text-sm">
          <p className="font-medium">还没有复盘记录</p>
          <p className="mt-1 text-muted-foreground">
            打开
            <Link href="/board" className="mx-1 underline">
              求职看板
            </Link>
            上的任意投递，点“面试复盘”旁的“复盘”按钮开始。
          </p>
        </div>
      )}
      {interviews && interviews.length > 0 && (
        <ul className="flex flex-col gap-2">
          {interviews.map((iv) => (
            <InterviewRow
              key={iv.id}
              interview={iv}
              title={`${appName.get(iv.application_id) ?? "投递"} · ${iv.round}`}
            />
          ))}
        </ul>
      )}
    </div>
  );
}
