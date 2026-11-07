"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Allow, parse } from "partial-json";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  type MatchAnalysis,
  type MatchRequest,
  type PrepItem,
  type PrepItemCreate,
  type PrepItemUpdate,
  matchApi,
  streamMatch,
} from "@/lib/api/match";

const reportKey = (appId: string) => ["match-report", appId] as const;
const prepKey = (appId: string) => ["prep-items", appId] as const;

export function useMatchReport(appId: string) {
  return useQuery({ queryKey: reportKey(appId), queryFn: () => matchApi.getReport(appId) });
}

export function usePrepItems(appId: string) {
  return useQuery({ queryKey: prepKey(appId), queryFn: () => matchApi.listPrep(appId) });
}

export type StreamState =
  | { status: "idle" }
  | { status: "streaming"; partial: Partial<MatchAnalysis>; chars: number; note?: string }
  | { status: "error"; message: string };

/**
 * 流式生成匹配分析。
 *
 * 模型输出的是一段 JSON，但在生成过程中它是“不完整”的（比如 {"score": 72, "summ）。
 * partial-json 能把这种半截 JSON 尽量解析出来，于是界面可以边生成边显示已经完成的字段。
 */
export function useMatchStream(appId: string) {
  const qc = useQueryClient();
  const [state, setState] = useState<StreamState>({ status: "idle" });
  const controller = useRef<AbortController | null>(null);

  // 离开页面时中断请求，后端会随之停止生成
  useEffect(() => () => controller.current?.abort(), []);

  const start = useCallback(
    async (request: MatchRequest) => {
      controller.current?.abort();
      const ac = new AbortController();
      controller.current = ac;
      let buffer = "";
      setState({ status: "streaming", partial: {}, chars: 0 });

      try {
        await streamMatch(
          appId,
          request,
          {
            onDelta: (text) => {
              buffer += text;
              let partial: Partial<MatchAnalysis> = {};
              try {
                // 只接受“完整的字符串、数字”，避免把写了一半的字显示出来又跳变
                partial = parse(buffer, Allow.ALL & ~Allow.STR & ~Allow.NUM);
              } catch {
                // 极少数情况下片段无法解析，保留上一次的结果即可
              }
              setState((s) =>
                s.status === "streaming" ? { ...s, partial, chars: buffer.length } : s,
              );
            },
            onReset: (reason) => {
              buffer = "";
              setState({ status: "streaming", partial: {}, chars: 0, note: reason });
            },
            onDone: (report) => {
              qc.setQueryData(reportKey(appId), report);
              qc.invalidateQueries({ queryKey: prepKey(appId) });
              setState({ status: "idle" });
            },
          },
          ac.signal,
        );
      } catch (err) {
        if (ac.signal.aborted) return;
        setState({ status: "error", message: err instanceof Error ? err.message : "生成失败" });
      }
    },
    [appId, qc],
  );

  const cancel = useCallback(() => {
    controller.current?.abort();
    setState({ status: "idle" });
  }, []);

  return { state, start, cancel };
}

// ---------- 备考清单 ----------

export function useCreatePrep(appId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: PrepItemCreate) => matchApi.createPrep(appId, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: prepKey(appId) }),
  });
}

/** 勾选 / 取消勾选：乐观更新，点了立刻打勾，不等服务器 */
export function useUpdatePrep(appId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: PrepItemUpdate }) =>
      matchApi.updatePrep(id, data),
    onMutate: async ({ id, data }) => {
      await qc.cancelQueries({ queryKey: prepKey(appId) });
      const previous = qc.getQueryData<PrepItem[]>(prepKey(appId));
      qc.setQueryData<PrepItem[]>(prepKey(appId), (items) =>
        items?.map((i) => (i.id === id ? { ...i, ...(data as Partial<PrepItem>) } : i)),
      );
      return { previous };
    },
    onError: (_e, _v, ctx) => ctx?.previous && qc.setQueryData(prepKey(appId), ctx.previous),
    onSettled: () => qc.invalidateQueries({ queryKey: prepKey(appId) }),
  });
}

export function useDeletePrep(appId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => matchApi.removePrep(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: prepKey(appId) }),
  });
}
