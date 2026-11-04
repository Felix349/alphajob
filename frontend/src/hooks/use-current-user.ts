"use client";

import { useQuery } from "@tanstack/react-query";

import { authApi } from "@/lib/api/auth";

export const CURRENT_USER_KEY = ["auth", "me"] as const;

export function useCurrentUser() {
  return useQuery({
    queryKey: CURRENT_USER_KEY,
    queryFn: authApi.me,
    retry: false, // 401 时不要重试
    staleTime: 5 * 60 * 1000,
  });
}
