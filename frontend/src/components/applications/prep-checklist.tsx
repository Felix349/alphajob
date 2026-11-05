"use client";

import { Plus, Sparkles, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { useCreatePrep, useDeletePrep, usePrepItems, useUpdatePrep } from "@/hooks/use-match";
import type { PrepCategory } from "@/lib/api/match";
import { cn } from "@/lib/utils";

const CATEGORY: Record<PrepCategory, string> = {
  knowledge: "知识点",
  project: "项目",
  question: "练习",
  other: "其他",
};

export function PrepChecklist({ appId }: { appId: string }) {
  const { data: items = [], isPending } = usePrepItems(appId);
  const create = useCreatePrep(appId);
  const update = useUpdatePrep(appId);
  const remove = useDeletePrep(appId);
  const [draft, setDraft] = useState("");

  const done = items.filter((i) => i.done).length;

  function add(e: React.FormEvent) {
    e.preventDefault();
    const content = draft.trim();
    if (!content) return;
    create.mutate(
      { content, category: "other", priority: 2 },
      { onSuccess: () => setDraft(""), onError: (err) => toast.error(err.message) },
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>备考清单</CardTitle>
        {items.length > 0 && (
          <div className="mt-2 flex items-center gap-2 text-xs text-muted-foreground">
            <Progress value={(done / items.length) * 100} className="h-1.5 flex-1" />
            {done}/{items.length}
          </div>
        )}
      </CardHeader>
      <CardContent className="flex flex-col gap-3 text-sm">
        {!isPending && items.length === 0 && (
          <p className="text-muted-foreground">
            生成岗位匹配分析后，这里会出现针对性的备考任务；也可以自己添加。
          </p>
        )}
        <ul className="flex flex-col gap-1">
          {items.map((item) => (
            <li
              key={item.id}
              className="group flex items-start gap-2.5 rounded-md px-1.5 py-1.5 hover:bg-muted/50"
            >
              <Checkbox
                className="mt-0.5"
                checked={item.done}
                aria-label={item.content}
                onCheckedChange={(checked) =>
                  update.mutate({ id: item.id, data: { done: Boolean(checked) } })
                }
              />
              <div className="min-w-0 flex-1">
                <p className={cn(item.done && "text-muted-foreground line-through")}>
                  {item.content}
                </p>
                <div className="mt-0.5 flex items-center gap-1.5 text-xs text-muted-foreground">
                  {item.priority === 1 && !item.done && <span className="text-rose-600">优先</span>}
                  <span>{CATEGORY[item.category]}</span>
                  {item.source === "ai" && <Sparkles className="size-3" aria-label="AI 生成" />}
                </div>
              </div>
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label="删除"
                className="opacity-0 group-hover:opacity-100 focus-visible:opacity-100"
                onClick={() =>
                  remove.mutate(item.id, { onError: (err) => toast.error(err.message) })
                }
              >
                <Trash2 className="size-3.5" />
              </Button>
            </li>
          ))}
        </ul>
        <form onSubmit={add} className="flex gap-2">
          <Input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="添加一条备考任务"
            aria-label="添加备考任务"
          />
          <Button
            type="submit"
            size="icon"
            variant="outline"
            aria-label="添加"
            disabled={!draft.trim()}
          >
            <Plus className="size-4" />
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
