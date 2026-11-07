"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { resumeApi, type ResumeLanguage } from "@/lib/api/resume";

const key = (language: ResumeLanguage) => ["resume", language] as const;

export function useResume(language: ResumeLanguage) {
  return useQuery({ queryKey: key(language), queryFn: () => resumeApi.get(language) });
}

function useResumeMutation<A>(language: ResumeLanguage, fn: (arg: A) => Promise<unknown>) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: key(language) });
      // 简历变了，已有的匹配分析可能“过期”，让它们重新拉取 stale 标记
      qc.invalidateQueries({ queryKey: ["match-report"] });
    },
  });
}

export const useSaveResume = (language: ResumeLanguage) =>
  useResumeMutation(language, (content: string) => resumeApi.save(language, content));
export const useUploadResume = (language: ResumeLanguage) =>
  useResumeMutation(language, (file: File) => resumeApi.upload(language, file));
export const useDeleteResume = (language: ResumeLanguage) =>
  useResumeMutation(language, () => resumeApi.remove(language));
