import { apiFetch } from "./client";
import type { components } from "./schema";

export type Resume = components["schemas"]["ResumeOut"];
export type ResumeLanguage = Resume["language"];

export const RESUME_LANGUAGES: { value: ResumeLanguage; label: string }[] = [
  { value: "zh", label: "中文简历" },
  { value: "en", label: "英文简历" },
];

const url = (path: string, language: ResumeLanguage) => `${path}?language=${language}`;

export const resumeApi = {
  get: (language: ResumeLanguage) => apiFetch<Resume | null>(url("/resume", language)),
  save: (language: ResumeLanguage, content_md: string) =>
    apiFetch<Resume>(url("/resume", language), {
      method: "PUT",
      body: JSON.stringify({ content_md }),
    }),
  upload: (language: ResumeLanguage, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return apiFetch<Resume>(url("/resume/upload", language), { method: "POST", body: form });
  },
  remove: (language: ResumeLanguage) =>
    apiFetch<void>(url("/resume", language), { method: "DELETE" }),
};
