"use client";

import { Sparkles } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { useParseJd, useUpdateApplication } from "@/hooks/use-applications";
import type { ApplicationDetail } from "@/lib/api/applications";

/** 新建投递时跳过了 JD：在这里补上，保存后顺便尝试智能解析（没配 Key 时只保存原文）。 */
function AddJd({ appId }: { appId: string }) {
  const [text, setText] = useState("");
  const update = useUpdateApplication();
  const parse = useParseJd();
  const busy = update.isPending || parse.isPending;

  function save() {
    const jd = text.trim();
    update.mutate(
      { id: appId, data: { jd_text: jd } },
      {
        onSuccess: () =>
          parse.mutate(jd, {
            onSuccess: (result) =>
              update.mutate(
                { id: appId, data: { jd_parsed: result } },
                { onSuccess: () => toast.success("JD 已保存并解析") },
              ),
            onError: () => toast.success("JD 已保存（智能解析暂不可用）"),
          }),
        onError: (err) => toast.error(err.message),
      },
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <p className="text-muted-foreground">还没有 JD。粘贴进来，岗位匹配分析需要用到它。</p>
      <Textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="把招聘页上的岗位描述整段复制到这里……"
        className="min-h-32"
        aria-label="岗位描述"
      />
      <div className="flex justify-end">
        <Button size="sm" onClick={save} disabled={text.trim().length < 20 || busy}>
          {busy ? "保存中…" : "保存 JD"}
        </Button>
      </div>
    </div>
  );
}

export function JdPanel({ app }: { app: ApplicationDetail }) {
  const parse = useParseJd();
  const update = useUpdateApplication();
  const parsed = app.jd_parsed;

  function reparse() {
    if (!app.jd_text) return;
    parse.mutate(app.jd_text, {
      onSuccess: (result) =>
        update.mutate(
          { id: app.id, data: { jd_parsed: result } },
          { onSuccess: () => toast.success("JD 已重新解析") },
        ),
      onError: (err) => toast.error(err.message),
    });
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>岗位描述</CardTitle>
        {app.jd_text && (
          <Button size="sm" variant="outline" onClick={reparse} disabled={parse.isPending}>
            <Sparkles className="size-4" />
            {parse.isPending ? "解析中…" : parsed ? "重新解析" : "智能解析"}
          </Button>
        )}
      </CardHeader>
      <CardContent className="flex flex-col gap-4 text-sm">
        {!app.jd_text && <AddJd appId={app.id} />}
        {parsed && (
          <>
            <p className="rounded-lg bg-muted/50 p-3 font-medium">{parsed.summary}</p>
            <Meta parsed={parsed} />
            {parsed.tech_stack.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {parsed.tech_stack.map((t) => (
                  <Badge key={t} variant="secondary">
                    {t}
                  </Badge>
                ))}
              </div>
            )}
            <List title="岗位职责" items={parsed.responsibilities} />
            <List title="任职要求" items={parsed.requirements} />
            <List title="加分项" items={parsed.bonus} />
          </>
        )}
        {app.jd_text && (
          <details className="rounded-lg border p-3">
            <summary className="cursor-pointer text-muted-foreground">查看 JD 原文</summary>
            <p className="mt-2 whitespace-pre-wrap">{app.jd_text}</p>
          </details>
        )}
      </CardContent>
    </Card>
  );
}

function Meta({ parsed }: { parsed: NonNullable<ApplicationDetail["jd_parsed"]> }) {
  const items = [
    ["类型", parsed.job_type],
    ["薪资", parsed.salary],
    ["截止", parsed.deadline],
  ].filter(([, v]) => v);
  if (items.length === 0) return null;
  return (
    <dl className="flex flex-wrap gap-x-6 gap-y-1 text-muted-foreground">
      {items.map(([k, v]) => (
        <div key={k} className="flex gap-1">
          <dt>{k}：</dt>
          <dd className="text-foreground">{v}</dd>
        </div>
      ))}
    </dl>
  );
}

function List({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div>
      <h3 className="mb-1 font-medium">{title}</h3>
      <ul className="list-disc space-y-0.5 pl-5 text-muted-foreground">
        {items.map((item, i) => (
          <li key={i}>{item}</li>
        ))}
      </ul>
    </div>
  );
}
