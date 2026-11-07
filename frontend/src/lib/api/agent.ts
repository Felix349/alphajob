import { readSse } from "@/lib/sse";

import { ApiError, apiFetch, apiRequest } from "./client";
import type { components } from "./schema";

type S = components["schemas"];

export type AgentAction = S["AgentActionOut"];
export type PlanKind = "today" | "week";

// plan 字段在接口里是通用对象，这里按后端 schemas/agent.py 的 TodayPlan / WeekPlan 定义具体结构
export type TodayPlanData = {
  focus: string;
  items: {
    title: string;
    reason: string;
    minutes: number;
    priority: 1 | 2 | 3;
    application_id: string | null;
  }[];
};
export type WeekPlanData = {
  overview: string;
  key_dates: string[];
  days: { date: string; focus: string; tasks: string[] }[];
};
export type Plan = Omit<S["PlanOut"], "plan"> & { plan: TodayPlanData | WeekPlanData };

/** 浏览器所在时区：Agent 理解“今天”“下周三”要用用户的本地时间 */
export const timezone = () => Intl.DateTimeFormat().resolvedOptions().timeZone;

export const agentApi = {
  getPlan: (kind: PlanKind) =>
    apiFetch<Plan | null>(`/agent/plan?kind=${kind}&timezone=${encodeURIComponent(timezone())}`),
  createPlan: (kind: PlanKind) =>
    apiFetch<Plan>("/agent/plan", {
      method: "POST",
      body: JSON.stringify({ kind, timezone: timezone() }),
    }),
  toggleItem: (planId: string, index: number, done: boolean) =>
    apiFetch<Plan>(`/agent/plan/${planId}`, {
      method: "PATCH",
      body: JSON.stringify({ index, done }),
    }),
  confirm: (id: string) =>
    apiFetch<AgentAction>(`/agent/actions/${id}/confirm`, { method: "POST" }),
  cancel: (id: string) => apiFetch<AgentAction>(`/agent/actions/${id}/cancel`, { method: "POST" }),
};

export type ChatEvent =
  | { event: "thinking"; data: { text: string } }
  | { event: "tool_call"; data: { id: string; name: string; arguments: Record<string, unknown> } }
  | { event: "tool_result"; data: { id: string; name: string; summary: string; ok: boolean } }
  | { event: "proposal"; data: { id: string; tool: string; description: string } }
  | { event: "message"; data: { text: string } }
  | { event: "error"; data: { detail: string } };

export async function streamChat(
  messages: { role: "user" | "assistant"; content: string }[],
  onEvent: (e: ChatEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  const res = await apiRequest("/agent/chat", {
    method: "POST",
    body: JSON.stringify({ messages, timezone: timezone() }),
    headers: { Accept: "text/event-stream" },
    signal,
  });
  for await (const { event, data } of readSse(res, signal)) {
    const parsed = { event, data: JSON.parse(data) } as ChatEvent;
    if (parsed.event === "error") throw new ApiError(502, parsed.data.detail);
    onEvent(parsed);
  }
}

/** 工具名 → 给用户看的中文说明 */
export const TOOL_LABEL: Record<string, string> = {
  list_applications: "查看投递列表",
  get_application: "查看投递详情",
  list_events: "查看日程",
  list_prep_items: "查看备考清单",
  list_weak_points: "查看薄弱点",
  search_questions: "搜索题库",
  update_application_stage: "修改投递阶段",
  create_event: "添加日程",
  add_prep_item: "添加备考任务",
  set_prep_item_done: "更新备考任务",
  resolve_weak_point: "标记薄弱点已解决",
};
