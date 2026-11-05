import { apiFetch } from "./client";
import type { components } from "./schema";

export type Resume = components["schemas"]["ResumeOut"];

export const resumeApi = {
  get: () => apiFetch<Resume | null>("/resume"),
  save: (content_md: string) =>
    apiFetch<Resume>("/resume", { method: "PUT", body: JSON.stringify({ content_md }) }),
  upload: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return apiFetch<Resume>("/resume/upload", { method: "POST", body: form });
  },
  remove: () => apiFetch<void>("/resume", { method: "DELETE" }),
};
