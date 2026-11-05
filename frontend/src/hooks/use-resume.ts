"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { resumeApi } from "@/lib/api/resume";

const KEY = ["resume"] as const;

export function useResume() {
  return useQuery({ queryKey: KEY, queryFn: resumeApi.get });
}

function useResumeMutation<A>(fn: (arg: A) => Promise<unknown>) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEY });
      // 简历变了，已有的匹配分析可能“过期”，让它们重新拉取 stale 标记
      qc.invalidateQueries({ queryKey: ["match-report"] });
    },
  });
}

export const useSaveResume = () => useResumeMutation((content: string) => resumeApi.save(content));
export const useUploadResume = () => useResumeMutation((file: File) => resumeApi.upload(file));
export const useDeleteResume = () => useResumeMutation(() => resumeApi.remove());
