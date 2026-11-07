"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";

import { type ChatEvent, type PlanKind, agentApi, streamChat } from "@/lib/api/agent";

const planKey = (kind: PlanKind) => ["agent-plan", kind] as const;

export function usePlan(kind: PlanKind) {
  return useQuery({ queryKey: planKey(kind), queryFn: () => agentApi.getPlan(kind) });
}

export function useGeneratePlan(kind: PlanKind) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => agentApi.createPlan(kind),
    onSuccess: (plan) => qc.setQueryData(planKey(kind), plan),
  });
}

export function useTogglePlanItem() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ planId, index, done }: { planId: string; index: number; done: boolean }) =>
      agentApi.toggleItem(planId, index, done),
    onSuccess: (plan) => qc.setQueryData(planKey("today"), plan),
  });
}

// ---------- 对话 ----------

export type Step =
  | { kind: "thinking"; text: string }
  | { kind: "tool"; id: string; name: string; summary?: string; ok?: boolean };

export type Proposal = {
  id: string;
  description: string;
  status: "pending" | "done" | "cancelled" | "failed" | "working";
  result?: string | null;
};

type HistoryMessage = { role: "user" | "assistant"; content: string };

export type ChatTurn =
  | { role: "user"; text: string }
  | { role: "assistant"; steps: Step[]; proposals: Proposal[]; text: string; error?: string };

/**
 * 对话状态全部保存在前端：每次发送时把文字历史整段发给后端（后端不存聊天记录）。
 * 工具调用的过程（steps）只用于展示，不再发回给模型：每轮对话模型都会重新用工具查最新数据。
 */
export function useAgentChat() {
  const qc = useQueryClient();
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [busy, setBusy] = useState(false);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);

  const updateLast = (fn: (t: Extract<ChatTurn, { role: "assistant" }>) => void) =>
    setTurns((prev) => {
      const next = [...prev];
      const last = next[next.length - 1];
      if (last?.role === "assistant") {
        const copy = { ...last, steps: [...last.steps], proposals: [...last.proposals] };
        fn(copy);
        next[next.length - 1] = copy;
      }
      return next;
    });

  const send = useCallback(
    async (text: string) => {
      const past = turns.flatMap<HistoryMessage>((t) =>
        t.role === "user"
          ? [{ role: "user", content: t.text }]
          : t.text
            ? [{ role: "assistant", content: t.text }]
            : [],
      );
      // 只带最近 20 条，避免上下文无限增长
      const latest: HistoryMessage = { role: "user", content: text };
      const history = [...past, latest].slice(-20);

      setTurns((prev) => [
        ...prev,
        { role: "user", text },
        { role: "assistant", steps: [], proposals: [], text: "" },
      ]);
      setBusy(true);
      const ac = new AbortController();
      controller.current = ac;

      const onEvent = (e: ChatEvent) =>
        updateLast((t) => {
          if (e.event === "thinking") t.steps.push({ kind: "thinking", text: e.data.text });
          if (e.event === "tool_call")
            t.steps.push({ kind: "tool", id: e.data.id, name: e.data.name });
          if (e.event === "tool_result") {
            const i = t.steps.findIndex((s) => s.kind === "tool" && s.id === e.data.id);
            if (i >= 0)
              t.steps[i] = { ...t.steps[i], summary: e.data.summary, ok: e.data.ok } as Step;
          }
          if (e.event === "proposal") {
            t.proposals.push({ id: e.data.id, description: e.data.description, status: "pending" });
            const i = t.steps.findIndex((s) => s.kind === "tool" && !s.summary);
            if (i >= 0)
              t.steps[i] = { ...t.steps[i], summary: "已生成待确认操作", ok: true } as Step;
          }
          if (e.event === "message") t.text = e.data.text;
        });

      try {
        await streamChat(history, onEvent, ac.signal);
      } catch (err) {
        if (!ac.signal.aborted)
          updateLast((t) => (t.error = err instanceof Error ? err.message : "出错了"));
      } finally {
        setBusy(false);
      }
    },
    [turns],
  );

  const resolve = useCallback(
    async (id: string, how: "confirm" | "cancel") => {
      const patch = (p: Partial<Proposal>) =>
        setTurns((prev) =>
          prev.map((t) =>
            t.role === "assistant"
              ? { ...t, proposals: t.proposals.map((x) => (x.id === id ? { ...x, ...p } : x)) }
              : t,
          ),
        );
      patch({ status: "working" });
      try {
        const action = await (how === "confirm" ? agentApi.confirm(id) : agentApi.cancel(id));
        patch({ status: action.status, result: action.result });
        // 数据被改动了：让看板、日历、备考清单等页面重新拉取
        if (action.status === "done") qc.invalidateQueries();
      } catch (err) {
        patch({ status: "failed", result: err instanceof Error ? err.message : "操作失败" });
      }
    },
    [qc],
  );

  const reset = useCallback(() => {
    controller.current?.abort();
    setTurns([]);
    setBusy(false);
  }, []);

  return { turns, busy, send, resolve, reset };
}
