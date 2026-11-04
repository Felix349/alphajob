"use client";

import { ExternalLink, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { useCreateEvent, useDeleteEvent } from "@/hooks/use-applications";
import type { EventType, JobEvent } from "@/lib/api/applications";
import { formatDateTime, localInputToIso, relativeDay } from "@/lib/format";
import { EVENT_TYPES, EVENT_TYPE_COLOR, EVENT_TYPE_LABEL } from "@/lib/stages";
import { cn } from "@/lib/utils";

export function EventPanel({ appId, events }: { appId: string; events: JobEvent[] }) {
  const [adding, setAdding] = useState(false);
  const remove = useDeleteEvent(appId);
  // 在首次渲染时取一次“当前时间”，用来把过去的日程置灰（渲染函数里不能直接调用 Date.now）
  const [now] = useState(() => Date.now());

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>日程</CardTitle>
        {!adding && (
          <Button size="sm" variant="outline" onClick={() => setAdding(true)}>
            <Plus className="size-4" />
            添加
          </Button>
        )}
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {adding && <EventForm appId={appId} onDone={() => setAdding(false)} />}
        {events.length === 0 && !adding && (
          <p className="text-sm text-muted-foreground">
            还没有日程。笔试、面试时间记在这里，会显示在日历和看板卡片上。
          </p>
        )}
        <ul className="flex flex-col gap-2">
          {events.map((e) => {
            const past = new Date(e.start_at).getTime() < now;
            return (
              <li
                key={e.id}
                className={cn("flex items-start gap-3 rounded-lg border p-3", past && "opacity-60")}
              >
                <span
                  className="mt-1.5 size-2 shrink-0 rounded-full"
                  style={{ background: EVENT_TYPE_COLOR[e.type] }}
                />
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium">
                    {EVENT_TYPE_LABEL[e.type]} · {e.title}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {formatDateTime(e.start_at)}（{relativeDay(e.start_at)}）
                  </div>
                  {e.link && (
                    <a
                      href={e.link}
                      target="_blank"
                      rel="noreferrer"
                      className="mt-1 inline-flex items-center gap-1 text-xs underline"
                    >
                      <ExternalLink className="size-3" />
                      打开链接
                    </a>
                  )}
                  {e.note && <p className="mt-1 text-xs whitespace-pre-wrap">{e.note}</p>}
                </div>
                <Button
                  size="icon-sm"
                  variant="ghost"
                  aria-label="删除日程"
                  disabled={remove.isPending}
                  onClick={() =>
                    remove.mutate(e.id, { onError: (err) => toast.error(err.message) })
                  }
                >
                  <Trash2 className="size-4" />
                </Button>
              </li>
            );
          })}
        </ul>
      </CardContent>
    </Card>
  );
}

function EventForm({ appId, onDone }: { appId: string; onDone: () => void }) {
  const create = useCreateEvent(appId);
  const [type, setType] = useState<EventType>("interview");
  const [title, setTitle] = useState("一面");
  const [start, setStart] = useState("");
  const [link, setLink] = useState("");

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim() || !start) {
      toast.error("请填写标题和时间");
      return;
    }
    create.mutate(
      {
        type,
        title: title.trim(),
        start_at: localInputToIso(start),
        link: link.trim() || null,
      },
      {
        onSuccess: () => {
          toast.success("日程已添加");
          onDone();
        },
        onError: (err) => toast.error(err.message),
      },
    );
  }

  return (
    <form onSubmit={submit} className="grid gap-3 rounded-lg border bg-muted/30 p-3">
      <div className="grid grid-cols-2 gap-2">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="event-type">类型</Label>
          <NativeSelect
            id="event-type"
            value={type}
            onChange={(e) => setType(e.target.value as EventType)}
          >
            {EVENT_TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </NativeSelect>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="event-title">标题</Label>
          <Input id="event-title" value={title} onChange={(e) => setTitle(e.target.value)} />
        </div>
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="event-start">时间</Label>
        <Input
          id="event-start"
          type="datetime-local"
          value={start}
          onChange={(e) => setStart(e.target.value)}
        />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="event-link">链接（可选）</Label>
        <Input
          id="event-link"
          value={link}
          onChange={(e) => setLink(e.target.value)}
          placeholder="会议或笔试链接"
        />
      </div>
      <div className="flex justify-end gap-2">
        <Button type="button" size="sm" variant="ghost" onClick={onDone}>
          取消
        </Button>
        <Button type="submit" size="sm" disabled={create.isPending}>
          保存
        </Button>
      </div>
    </form>
  );
}
