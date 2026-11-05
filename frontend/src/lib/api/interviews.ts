import { apiFetch } from "./client";
import type { components } from "./schema";

type S = components["schemas"];

export type Interview = S["InterviewOut"];
export type InterviewDetail = S["InterviewDetail"];
export type InterviewStatus = S["InterviewStatus"];
export type Question = S["QuestionOut"];
export type BankQuestion = S["QuestionBankItem"];
export type Mastery = S["Mastery"];

export type NewInterview = {
  round: string;
  heldOn?: string;
  text?: string;
  audio?: Blob;
  audioName?: string;
};

export type QuestionFilters = {
  company?: string;
  tag?: string;
  mastery?: Mastery;
  q?: string;
};

/** 这些状态表示后台还在处理，前端需要定时刷新 */
export const IN_PROGRESS: InterviewStatus[] = ["pending", "transcribing", "analyzing"];

export const interviewsApi = {
  create: (appId: string, input: NewInterview) => {
    // 文件上传用 multipart/form-data：字段名和后端 Form(...) 参数一一对应
    const form = new FormData();
    form.append("round", input.round);
    if (input.heldOn) form.append("held_on", input.heldOn);
    if (input.text) form.append("text", input.text);
    if (input.audio) form.append("audio", input.audio, input.audioName ?? "recording.webm");
    return apiFetch<Interview>(`/applications/${appId}/interviews`, { method: "POST", body: form });
  },
  listForApp: (appId: string) => apiFetch<Interview[]>(`/applications/${appId}/interviews`),
  listAll: () => apiFetch<Interview[]>("/interviews"),
  get: (id: string) => apiFetch<InterviewDetail>(`/interviews/${id}`),
  retry: (id: string) => apiFetch<Interview>(`/interviews/${id}/retry`, { method: "POST" }),
  remove: (id: string) => apiFetch<void>(`/interviews/${id}`, { method: "DELETE" }),
  questions: (filters: QuestionFilters) => {
    const params = new URLSearchParams(
      Object.entries(filters).filter((e): e is [string, string] => Boolean(e[1])),
    );
    return apiFetch<BankQuestion[]>(`/questions${params.size ? `?${params}` : ""}`);
  },
  updateQuestion: (id: string, mastery: Mastery) =>
    apiFetch<Question>(`/questions/${id}`, { method: "PATCH", body: JSON.stringify({ mastery }) }),
};
