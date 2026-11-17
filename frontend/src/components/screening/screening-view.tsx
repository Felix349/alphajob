"use client";

import { ChevronRight, Plus } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useBatches } from "@/hooks/use-screening";
import type { Batch } from "@/lib/api/screening";

import { NewBatchDialog } from "./new-batch-dialog";

export const BATCH_STATUS: Record<string, string> = {
  collecting: "读取岗位中",
  screened: "已粗筛，待补充 JD",
  ranked: "已完成",
};

export function ScreeningView() {
  const { data: batches, isPending, error } = useBatches();
  const [open, setOpen] = useState(false);

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <div className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">岗位筛选</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            把一家公司的招聘列表交给
            AI：先粗筛出相关的岗位，再对照你的简历逐个精排，快速找到最值得投的几个。
          </p>
        </div>
        <Button onClick={() => setOpen(true)}>
          <Plus className="size-4" />
          新建筛选
        </Button>
      </div>

      {isPending && <Skeleton className="h-40 w-full rounded-xl" />}
      {error && <p className="text-sm text-destructive">加载失败：{error.message}</p>}
      {batches && batches.length === 0 && (
        <div className="rounded-xl border border-dashed p-12 text-center text-sm">
          <p className="font-medium">还没有筛选记录</p>
          <p className="mt-1 text-muted-foreground">
            点“新建筛选”，然后粘贴某家公司招聘列表页的内容。
          </p>
        </div>
      )}
      {batches && batches.length > 0 && (
        <ul className="flex flex-col gap-2">
          {batches.map((b) => (
            <BatchRow key={b.id} batch={b} />
          ))}
        </ul>
      )}

      <NewBatchDialog open={open} onOpenChange={setOpen} />
    </div>
  );
}

function BatchRow({ batch }: { batch: Batch }) {
  return (
    <li>
      <Link
        href={`/screening/${batch.id}`}
        className="flex items-center gap-4 rounded-lg border p-4 transition-colors hover:bg-muted/50"
      >
        <div className="flex-1">
          <div className="font-medium">{batch.company}</div>
          <div className="mt-0.5 text-xs text-muted-foreground">
            {BATCH_STATUS[batch.status] ?? batch.status} · {batch.total_jobs} 个岗位
            {batch.shortlisted_jobs > 0 && ` · 精排 ${batch.ranked_jobs}/${batch.shortlisted_jobs}`}
            {" · "}
            {new Date(batch.created_at).toLocaleDateString("zh-CN")}
          </div>
        </div>
        <ChevronRight className="size-4 text-muted-foreground" />
      </Link>
    </li>
  );
}
