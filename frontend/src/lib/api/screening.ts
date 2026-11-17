import { readSse } from "@/lib/sse";

import { apiFetch, apiRequest } from "./client";
import type { components } from "./schema";

type S = components["schemas"];

export type Batch = S["BatchOut"];
export type BatchDetail = S["BatchDetail"];
export type BatchCreate = S["BatchCreate"];
export type ScreeningJob = S["JobOut"];
export type ScreenResult = S["ScreenResult"];
export type AddJobsResult = S["AddJobsResult"];
export type JobType = NonNullable<S["ScreeningFilters"]["job_types"]>[number];

export const JOB_TYPES: JobType[] = ["校招", "实习", "社招"];

/** 精排结果（后端 QuickMatch，存在 rank_result 里，接口上是任意 JSON，这里补上类型） */
export type RankResult = {
  requirements: {
    requirement: string;
    importance: "required" | "preferred";
    level: "strong" | "partial" | "missing";
    evidence: string | null;
  }[];
  strength: string;
  gap: string;
  score: number;
  resume_language: "zh" | "en";
};

export const rankResultOf = (job: ScreeningJob) => job.rank_result as RankResult | null;

const json = (data: unknown) => ({ method: "POST", body: JSON.stringify(data) });

export const screeningApi = {
  list: () => apiFetch<Batch[]>("/screening/batches"),
  get: (id: string) => apiFetch<BatchDetail>(`/screening/batches/${id}`),
  create: (data: BatchCreate) => apiFetch<BatchDetail>("/screening/batches", json(data)),
  remove: (id: string) => apiFetch<void>(`/screening/batches/${id}`, { method: "DELETE" }),
  extract: (id: string, text: string) =>
    apiFetch<AddJobsResult>(`/screening/batches/${id}/extract`, json({ text })),
  screen: (id: string) => apiFetch<ScreenResult>(`/screening/batches/${id}/screen`, json({})),
  setJd: (jobId: string, jd_text: string) =>
    apiFetch<ScreeningJob>(`/screening/jobs/${jobId}/jd`, {
      method: "PUT",
      body: JSON.stringify({ jd_text }),
    }),
  importJob: (jobId: string) =>
    apiFetch<{ application_id: string }>(`/screening/jobs/${jobId}/import`, json({})),
};

export type RankHandlers = {
  onStart: (total: number) => void;
  onJob: (job: ScreeningJob, done: number, total: number) => void;
  onDone: (batch: BatchDetail) => void;
};

/** 精排：SSE 流式接收，每完成一个岗位推送一次。开始前的检查失败时抛出 ApiError（400）。 */
export async function streamRank(
  batchId: string,
  handlers: RankHandlers,
  signal: AbortSignal,
): Promise<void> {
  const res = await apiRequest(`/screening/batches/${batchId}/rank`, {
    method: "POST",
    headers: { Accept: "text/event-stream" },
    signal,
  });
  for await (const { event, data } of readSse(res, signal)) {
    const payload = JSON.parse(data);
    if (event === "start") handlers.onStart(payload.total);
    else if (event === "job") handlers.onJob(payload.job, payload.done, payload.total);
    else if (event === "done") handlers.onDone(payload as BatchDetail);
  }
}
