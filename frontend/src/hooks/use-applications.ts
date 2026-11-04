"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  type Application,
  type ApplicationCreate,
  type ApplicationUpdate,
  type JobEventCreate,
  applicationsApi,
  eventsApi,
} from "@/lib/api/applications";

export const keys = {
  list: ["applications"] as const,
  detail: (id: string) => ["applications", id] as const,
  calendar: ["calendar"] as const,
};

export function useApplications() {
  return useQuery({ queryKey: keys.list, queryFn: applicationsApi.list });
}

export function useApplication(id: string) {
  return useQuery({ queryKey: keys.detail(id), queryFn: () => applicationsApi.get(id) });
}

export function useCreateApplication() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: ApplicationCreate) => applicationsApi.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.list }),
  });
}

/**
 * 更新投递记录。带乐观更新：拖拽卡片时界面立即变化，不用等服务器返回；
 * 如果请求失败，回滚到修改前的数据。
 */
export function useUpdateApplication() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: ApplicationUpdate }) =>
      applicationsApi.update(id, data),
    onMutate: async ({ id, data }) => {
      await qc.cancelQueries({ queryKey: keys.list });
      const previous = qc.getQueryData<Application[]>(keys.list);
      if (previous) {
        qc.setQueryData<Application[]>(
          keys.list,
          previous.map((a) =>
            a.id === id
              ? {
                  ...a,
                  ...(data.stage ? { stage: data.stage } : {}),
                  ...(data.position != null ? { position: data.position } : {}),
                }
              : a,
          ),
        );
      }
      return { previous };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.previous) qc.setQueryData(keys.list, ctx.previous);
    },
    onSuccess: (detail) => qc.setQueryData(keys.detail(detail.id), detail),
    onSettled: () => {
      qc.invalidateQueries({ queryKey: keys.list });
      qc.invalidateQueries({ queryKey: keys.calendar });
    },
  });
}

export function useDeleteApplication() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => applicationsApi.remove(id),
    onSuccess: (_d, id) => {
      qc.removeQueries({ queryKey: keys.detail(id) });
      qc.invalidateQueries({ queryKey: keys.list });
      qc.invalidateQueries({ queryKey: keys.calendar });
    },
  });
}

export function useParseJd() {
  return useMutation({ mutationFn: (jdText: string) => applicationsApi.parseJd(jdText) });
}

function useInvalidateEvents(appId: string) {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: keys.detail(appId) });
    qc.invalidateQueries({ queryKey: keys.list }); // 卡片上的“下一场”会变
    qc.invalidateQueries({ queryKey: keys.calendar });
  };
}

export function useCreateEvent(appId: string) {
  const invalidate = useInvalidateEvents(appId);
  return useMutation({
    mutationFn: (data: JobEventCreate) => eventsApi.create(appId, data),
    onSuccess: invalidate,
  });
}

export function useDeleteEvent(appId: string) {
  const invalidate = useInvalidateEvents(appId);
  return useMutation({ mutationFn: (id: string) => eventsApi.remove(id), onSuccess: invalidate });
}

export function useCalendarEvents(range: { start: Date; end: Date } | null) {
  return useQuery({
    queryKey: [...keys.calendar, range?.start.toISOString(), range?.end.toISOString()],
    queryFn: () => eventsApi.calendar(range!.start, range!.end),
    enabled: range !== null,
    placeholderData: (prev) => prev, // 切换月份时保留上一页数据，避免闪烁
  });
}
