import { readSse } from "@/lib/sse";

import { ApiError, apiFetch, apiRequest } from "./client";
import type { components } from "./schema";

type S = components["schemas"];

export type MatchAnalysis = S["MatchAnalysis"];
export type MatchReport = S["MatchReportOut"];
export type MatchRequest = S["MatchRequest"];
export type RequirementMatch = S["RequirementMatch"];
export type ResumeEdit = S["ResumeEdit"];
export type PrepItem = S["PrepItemOut"];
export type PrepItemCreate = S["PrepItemCreate"];
export type PrepItemUpdate = S["PrepItemUpdate"];
export type PrepCategory = S["PrepCategory"];

export const matchApi = {
  getReport: (appId: string) => apiFetch<MatchReport | null>(`/applications/${appId}/match-report`),
  listPrep: (appId: string) => apiFetch<PrepItem[]>(`/applications/${appId}/prep-items`),
  createPrep: (appId: string, data: PrepItemCreate) =>
    apiFetch<PrepItem>(`/applications/${appId}/prep-items`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updatePrep: (id: string, data: PrepItemUpdate) =>
    apiFetch<PrepItem>(`/prep-items/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  removePrep: (id: string) => apiFetch<void>(`/prep-items/${id}`, { method: "DELETE" }),
};

export type StreamHandlers = {
  onDelta: (text: string) => void;
  onReset: (reason: string) => void;
  onDone: (report: MatchReport) => void;
};

/** 生成匹配分析：POST 请求，以 SSE 流式接收。失败时抛出 ApiError。 */
export async function streamMatch(
  appId: string,
  request: MatchRequest,
  handlers: StreamHandlers,
  signal: AbortSignal,
): Promise<void> {
  // 开始前的检查（没有简历、没有 JD）失败时，后端返回普通的 400，这里会抛出 ApiError
  const res = await apiRequest(`/applications/${appId}/match-report`, {
    method: "POST",
    body: JSON.stringify(request),
    headers: { Accept: "text/event-stream" },
    signal,
  });

  for await (const { event, data } of readSse(res, signal)) {
    const payload = JSON.parse(data);
    if (event === "delta") handlers.onDelta(payload.text);
    else if (event === "reset") handlers.onReset(payload.reason);
    else if (event === "done") handlers.onDone(payload as MatchReport);
    else if (event === "error") throw new ApiError(502, payload.detail);
  }
}
