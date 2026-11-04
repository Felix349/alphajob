import { apiFetch } from "./client";
import type { components } from "./schema";

type S = components["schemas"];

export type Stage = S["Stage"];
export type EventType = S["EventType"];
export type Application = S["ApplicationOut"];
export type ApplicationDetail = S["ApplicationDetail"];
export type ApplicationCreate = S["ApplicationCreate"];
export type ApplicationUpdate = S["ApplicationUpdate"];
export type JobEvent = S["EventOut"];
export type JobEventCreate = S["EventCreate"];
export type JobEventUpdate = S["EventUpdate"];
export type CalendarEvent = S["CalendarEventOut"];
export type ParsedJD = S["ParsedJD"];

const json = (body: unknown) => JSON.stringify(body);

export const applicationsApi = {
  list: () => apiFetch<Application[]>("/applications"),
  get: (id: string) => apiFetch<ApplicationDetail>(`/applications/${id}`),
  create: (data: ApplicationCreate) =>
    apiFetch<ApplicationDetail>("/applications", { method: "POST", body: json(data) }),
  update: (id: string, data: ApplicationUpdate) =>
    apiFetch<ApplicationDetail>(`/applications/${id}`, { method: "PATCH", body: json(data) }),
  remove: (id: string) => apiFetch<void>(`/applications/${id}`, { method: "DELETE" }),
  parseJd: (jdText: string) =>
    apiFetch<ParsedJD>("/applications/parse-jd", {
      method: "POST",
      body: json({ jd_text: jdText }),
    }),
};

export const eventsApi = {
  create: (appId: string, data: JobEventCreate) =>
    apiFetch<JobEvent>(`/applications/${appId}/events`, { method: "POST", body: json(data) }),
  update: (id: string, data: JobEventUpdate) =>
    apiFetch<JobEvent>(`/events/${id}`, { method: "PATCH", body: json(data) }),
  remove: (id: string) => apiFetch<void>(`/events/${id}`, { method: "DELETE" }),
  calendar: (start: Date, end: Date) => {
    const q = new URLSearchParams({ start: start.toISOString(), end: end.toISOString() });
    return apiFetch<CalendarEvent[]>(`/events?${q}`);
  },
};
