"use client";

import { Check, CircleAlert, Loader2, RotateCcw, Send, Wrench, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { type ChatTurn, type Proposal, type Step, useAgentChat } from "@/hooks/use-agent";
import { TOOL_LABEL } from "@/lib/api/agent";
import { cn } from "@/lib/utils";

const SUGGESTIONS = [
  "我这周有哪些面试？",
  "哪个投递最需要优先准备？",
  "我最近暴露了哪些薄弱点？",
  "把下周三下午三点的北辰云二面记到日程里",
];

export function ChatPanel() {
  const { turns, busy, send, resolve, reset } = useAgentChat();
  const [draft, setDraft] = useState("");
  const bottom = useRef<HTMLDivElement>(null);

  // 有新内容时滚动到底部
  // 注意要用花括号：useEffect 只能返回清理函数或什么都不返回。
  // 新版浏览器的 scrollIntoView 会返回 Promise，直接作为箭头函数的返回值会被 React 当成清理函数去调用而报错
  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns]);

  function submit(text = draft) {
    const t = text.trim();
    if (!t || busy) return;
    setDraft("");
    send(t);
  }

  return (
    <Card className="flex h-[calc(100vh-8rem)] min-h-[520px] flex-col">
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>求职助手</CardTitle>
        {turns.length > 0 && (
          <Button size="sm" variant="ghost" onClick={reset} disabled={busy}>
            <RotateCcw className="size-3.5" />
            新对话
          </Button>
        )}
      </CardHeader>
      <CardContent className="flex min-h-0 flex-1 flex-col gap-3">
        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto pr-1 text-sm">
          {turns.length === 0 && (
            <div className="flex flex-col gap-2 py-6">
              <p className="text-muted-foreground">
                可以问我投递进度、日程、薄弱点，也可以让我帮你改数据。所有修改都会先请你确认。
              </p>
              <div className="flex flex-wrap gap-2">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => submit(s)}
                    className="rounded-full border px-3 py-1 text-xs hover:bg-muted"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}
          {turns.map((t, i) => (
            <Turn key={i} turn={t} live={busy && i === turns.length - 1} onResolve={resolve} />
          ))}
          <div ref={bottom} />
        </div>
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
        >
          <Textarea
            aria-label="输入消息"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              // Enter 发送，Shift + Enter 换行；输入法正在组字时不发送
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault();
                submit();
              }
            }}
            placeholder="问点什么，或者让我帮你记一场面试……"
            className="min-h-10 resize-none"
            rows={1}
          />
          <Button type="submit" size="icon" aria-label="发送" disabled={busy || !draft.trim()}>
            {busy ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

function Turn({
  turn,
  live,
  onResolve,
}: {
  turn: ChatTurn;
  live: boolean;
  onResolve: (id: string, how: "confirm" | "cancel") => void;
}) {
  if (turn.role === "user") {
    return (
      <div className="flex justify-end">
        <p className="max-w-[85%] rounded-2xl rounded-br-sm bg-primary px-3 py-2 whitespace-pre-wrap text-primary-foreground">
          {turn.text}
        </p>
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-2">
      {turn.steps.length > 0 && <Steps steps={turn.steps} />}
      {turn.proposals.map((p) => (
        <ProposalCard key={p.id} proposal={p} onResolve={onResolve} />
      ))}
      {turn.text && <p className="leading-relaxed whitespace-pre-wrap">{turn.text}</p>}
      {live && !turn.text && (
        <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Loader2 className="size-3 animate-spin" />
          思考中…
        </p>
      )}
      {turn.error && (
        <p className="flex items-center gap-1.5 text-destructive">
          <CircleAlert className="size-4" />
          {turn.error}
        </p>
      )}
    </div>
  );
}

/** 推理过程：调用了哪些工具、结果如何。默认折叠，只显示一行摘要。 */
function Steps({ steps }: { steps: Step[] }) {
  const tools = steps.filter((s) => s.kind === "tool");
  return (
    <details className="group rounded-lg border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
      <summary className="flex cursor-pointer list-none items-center gap-1.5">
        <Wrench className="size-3" />
        {tools.length > 0
          ? `调用了 ${tools.length} 次工具：${[...new Set(tools.map((s) => TOOL_LABEL[s.name] ?? s.name))].join("、")}`
          : "思考过程"}
      </summary>
      <ol className="mt-2 space-y-1">
        {steps.map((s, i) =>
          s.kind === "thinking" ? (
            <li key={i} className="italic">
              {s.text}
            </li>
          ) : (
            <li key={i} className="flex items-center gap-1.5">
              {s.summary === undefined ? (
                <Loader2 className="size-3 animate-spin" />
              ) : s.ok ? (
                <Check className="size-3 text-emerald-600" />
              ) : (
                <X className="size-3 text-rose-600" />
              )}
              <span className="font-mono">{s.name}</span>
              {s.summary && <span>· {s.summary}</span>}
            </li>
          ),
        )}
      </ol>
    </details>
  );
}

function ProposalCard({
  proposal,
  onResolve,
}: {
  proposal: Proposal;
  onResolve: (id: string, how: "confirm" | "cancel") => void;
}) {
  const settled = proposal.status !== "pending" && proposal.status !== "working";
  return (
    <div
      className={cn(
        "rounded-lg border p-3",
        proposal.status === "pending" && "border-amber-300 bg-amber-50 dark:bg-amber-950/30",
        proposal.status === "done" && "border-emerald-300 bg-emerald-50 dark:bg-emerald-950/30",
      )}
    >
      <p className="text-xs font-medium text-muted-foreground">需要你确认的操作</p>
      <p className="mt-1">{proposal.description}</p>
      {settled ? (
        <p
          className={cn(
            "mt-2 text-xs",
            proposal.status === "done"
              ? "text-emerald-700 dark:text-emerald-300"
              : "text-muted-foreground",
            proposal.status === "failed" && "text-destructive",
          )}
        >
          {proposal.status === "done" && `✓ ${proposal.result ?? "已完成"}`}
          {proposal.status === "cancelled" && "已取消"}
          {proposal.status === "failed" && `执行失败：${proposal.result ?? ""}`}
        </p>
      ) : (
        <div className="mt-2 flex gap-2">
          <Button
            size="sm"
            onClick={() => onResolve(proposal.id, "confirm")}
            disabled={proposal.status === "working"}
          >
            {proposal.status === "working" ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <Check className="size-3.5" />
            )}
            确认
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => onResolve(proposal.id, "cancel")}
            disabled={proposal.status === "working"}
          >
            取消
          </Button>
        </div>
      )}
    </div>
  );
}
