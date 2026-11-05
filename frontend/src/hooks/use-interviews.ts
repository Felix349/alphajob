"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  IN_PROGRESS,
  type Interview,
  type Mastery,
  type NewInterview,
  type QuestionFilters,
  interviewsApi,
} from "@/lib/api/interviews";

const keys = {
  all: ["interviews"] as const,
  forApp: (appId: string) => ["interviews", "app", appId] as const,
  detail: (id: string) => ["interviews", "detail", id] as const,
  questions: (f: QuestionFilters) => ["questions", f] as const,
};

/**
 * 轮询：后台还在处理时，每 2 秒刷新一次；处理完成（或失败）后自动停止。
 * 比 WebSocket 简单得多，对“几十秒到几分钟”的任务完全够用。
 */
const POLL_MS = 2000;
const pollWhile = (busy: boolean) => (busy ? POLL_MS : false);
const anyBusy = (list?: Interview[]) => Boolean(list?.some((i) => IN_PROGRESS.includes(i.status)));

export function useApplicationInterviews(appId: string) {
  return useQuery({
    queryKey: keys.forApp(appId),
    queryFn: () => interviewsApi.listForApp(appId),
    refetchInterval: (q) => pollWhile(anyBusy(q.state.data)),
  });
}

export function useAllInterviews() {
  return useQuery({
    queryKey: keys.all,
    queryFn: interviewsApi.listAll,
    refetchInterval: (q) => pollWhile(anyBusy(q.state.data)),
  });
}

export function useInterview(id: string) {
  const qc = useQueryClient();
  return useQuery({
    queryKey: keys.detail(id),
    queryFn: async () => {
      const detail = await interviewsApi.get(id);
      // 处理完成后，题库和列表里的数据也变了，顺便刷新
      if (detail.status === "done") qc.invalidateQueries({ queryKey: ["questions"] });
      return detail;
    },
    refetchInterval: (q) =>
      pollWhile(Boolean(q.state.data && IN_PROGRESS.includes(q.state.data.status))),
  });
}

function useInvalidateAll() {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: keys.all });
    qc.invalidateQueries({ queryKey: ["questions"] });
  };
}

export function useCreateInterview(appId: string) {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: (input: NewInterview) => interviewsApi.create(appId, input),
    onSuccess: invalidate,
  });
}

export function useRetryInterview() {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: (id: string) => interviewsApi.retry(id),
    onSuccess: invalidate,
  });
}

export function useDeleteInterview() {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: (id: string) => interviewsApi.remove(id),
    onSuccess: invalidate,
  });
}

export function useQuestions(filters: QuestionFilters) {
  return useQuery({
    queryKey: keys.questions(filters),
    queryFn: () => interviewsApi.questions(filters),
    placeholderData: (prev) => prev, // 切换筛选条件时保留旧数据，避免列表闪烁
  });
}

export function useUpdateMastery() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, mastery }: { id: string; mastery: Mastery }) =>
      interviewsApi.updateQuestion(id, mastery),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["questions"] });
      qc.invalidateQueries({ queryKey: ["interviews", "detail"] });
    },
  });
}
