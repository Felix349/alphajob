"use client";

import { Plus } from "lucide-react";
import { useState } from "react";

import { NewApplicationDialog } from "@/components/applications/new-application-dialog";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useApplications } from "@/hooks/use-applications";

import { Board } from "./board";

export function BoardView() {
  const { data, isPending, error } = useApplications();
  const [open, setOpen] = useState(false);

  const active = data?.filter((a) => a.stage !== "ended").length ?? 0;

  return (
    <div className="flex h-full flex-col">
      <div className="mb-6 flex items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">求职看板</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {data ? `进行中 ${active} 个 · 共 ${data.length} 个投递` : "拖动卡片来更新投递进度"}
          </p>
        </div>
        <Button onClick={() => setOpen(true)}>
          <Plus className="size-4" />
          新建投递
        </Button>
      </div>

      {isPending && (
        <div className="flex gap-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-64 w-64 shrink-0 rounded-xl" />
          ))}
        </div>
      )}
      {error && <p className="text-sm text-destructive">加载失败：{error.message}</p>}
      {data && data.length === 0 && (
        <div className="rounded-xl border border-dashed p-12 text-center">
          <p className="font-medium">还没有投递记录</p>
          <p className="mt-1 text-sm text-muted-foreground">
            点击“新建投递”，粘贴一段岗位描述试试 AI 解析。
          </p>
        </div>
      )}
      {data && data.length > 0 && <Board applications={data} />}

      <NewApplicationDialog open={open} onOpenChange={setOpen} />
    </div>
  );
}
