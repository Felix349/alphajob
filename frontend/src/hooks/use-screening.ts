"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  type BatchCreate,
  type BatchDetail,
  type ScreeningJob,
  screeningApi,
  streamRank,
} from "@/lib/api/screening";

const keys = {
  all: ["screening"] as const,
  detail: (id: string) => ["screening", id] as const,
};

export function useBatches() {
  return useQuery({ queryKey: keys.all, queryFn: screeningApi.list });
}

export function useBatch(id: string) {
  return useQuery({ queryKey: keys.detail(id), queryFn: () => screeningApi.get(id) });
}

/** 批次的任何变化之后：刷新详情和列表（列表上显示岗位数、进度） */
function useInvalidate() {
  const qc = useQueryClient();
  return (id?: string) => {
    qc.invalidateQueries({ queryKey: keys.all, exact: true });
    if (id) qc.invalidateQueries({ queryKey: keys.detail(id) });
  };
}

export function useCreateBatch() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (data: BatchCreate) => screeningApi.create(data),
    onSuccess: () => invalidate(),
  });
}

export function useDeleteBatch() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (id: string) => screeningApi.remove(id),
    onSuccess: () => invalidate(),
  });
}

export function useExtractJobs(id: string) {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (text: string) => screeningApi.extract(id, text),
    onSuccess: () => invalidate(id),
  });
}

export function useScreen(id: string) {
  const qc = useQueryClient();
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: () => screeningApi.screen(id),
    onSuccess: (result) => {
      qc.setQueryData(keys.detail(id), result.batch);
      invalidate();
    },
  });
}

/** 更新详情缓存里的某一个岗位：补 JD、精排逐个出结果、加入投递记录之后用 */
function useUpdateJobInCache(batchId: string) {
  const qc = useQueryClient();
  return useCallback(
    (job: Partial<ScreeningJob> & { id: string }) =>
      qc.setQueryData<BatchDetail>(keys.detail(batchId), (old) =>
        old ? { ...old, jobs: old.jobs.map((j) => (j.id === job.id ? { ...j, ...job } : j)) } : old,
      ),
    [qc, batchId],
  );
}

export function useSetJd(batchId: string) {
  const update = useUpdateJobInCache(batchId);
  return useMutation({
    mutationFn: ({ jobId, jdText }: { jobId: string; jdText: string }) =>
      screeningApi.setJd(jobId, jdText),
    onSuccess: (job) => update(job),
  });
}

export function useImportJob(batchId: string) {
  const update = useUpdateJobInCache(batchId);
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (jobId: string) => screeningApi.importJob(jobId),
    onSuccess: ({ application_id }, jobId) => {
      update({ id: jobId, application_id });
      qc.invalidateQueries({ queryKey: ["applications"] }); // 看板上多了一张“想投”卡片
    },
  });
}

type RankState =
  | { status: "idle" }
  | { status: "running"; done: number; total: number }
  | { status: "error"; message: string };

/** 精排：边收边更新缓存里对应的岗位，页面上一个个出现分数。 */
export function useRank(batchId: string) {
  const qc = useQueryClient();
  const update = useUpdateJobInCache(batchId);
  const invalidate = useInvalidate();
  const [state, setState] = useState<RankState>({ status: "idle" });
  const controller = useRef<AbortController | null>(null);

  // 离开页面时中断请求，后端随之取消还没开始的调用
  useEffect(() => () => controller.current?.abort(), []);

  const start = useCallback(async () => {
    controller.current?.abort();
    const ac = new AbortController();
    controller.current = ac;
    setState({ status: "running", done: 0, total: 0 });
    try {
      await streamRank(
        batchId,
        {
          onStart: (total) => setState({ status: "running", done: 0, total }),
          onJob: (job, done, total) => {
            update(job);
            setState({ status: "running", done, total });
          },
          onDone: (batch) => {
            qc.setQueryData(keys.detail(batchId), batch);
            invalidate();
          },
        },
        ac.signal,
      );
      setState({ status: "idle" });
    } catch (err) {
      if (ac.signal.aborted) return;
      setState({ status: "error", message: err instanceof Error ? err.message : String(err) });
    }
  }, [batchId, qc, update, invalidate]);

  return { state, start };
}
