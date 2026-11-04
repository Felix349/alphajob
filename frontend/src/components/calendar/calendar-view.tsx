"use client";

import FullCalendar from "@fullcalendar/react";
import dayGridPlugin from "@fullcalendar/react/daygrid";
import zhCnLocale from "@fullcalendar/react/locales/zh-cn";
import classicThemePlugin from "@fullcalendar/react/themes/classic";
import timeGridPlugin from "@fullcalendar/react/timegrid";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { useCalendarEvents } from "@/hooks/use-applications";
import { EVENT_TYPES, EVENT_TYPE_COLOR, EVENT_TYPE_LABEL } from "@/lib/stages";

import "@fullcalendar/react/skeleton.css";
import "@fullcalendar/react/themes/classic/theme.css";
import "@fullcalendar/react/themes/classic/palette.css";

export function CalendarView() {
  const router = useRouter();
  // 当前视图显示的时间范围，由日历组件在翻页时回调告诉我们
  const [range, setRange] = useState<{ start: Date; end: Date } | null>(null);
  const { data, error } = useCalendarEvents(range);

  const events = useMemo(
    () =>
      (data ?? []).map((e) => ({
        id: e.id,
        title: `${e.company} · ${e.title}`,
        start: e.start_at,
        end: e.end_at ?? undefined,
        color: EVENT_TYPE_COLOR[e.type],
        extendedProps: { applicationId: e.application_id, type: e.type },
      })),
    [data],
  );

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">日历</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            所有笔试、面试和截止日期。在投递详情页添加日程，点击日程可以跳转到对应投递。
          </p>
        </div>
        <ul className="flex gap-3 text-xs text-muted-foreground">
          {EVENT_TYPES.map((t) => (
            <li key={t.value} className="flex items-center gap-1">
              <span className="size-2 rounded-full" style={{ background: t.color }} />
              {t.label}
            </li>
          ))}
        </ul>
      </div>
      {error && <p className="text-sm text-destructive">加载失败：{error.message}</p>}
      <div className="rounded-xl border bg-card p-3">
        <FullCalendar
          plugins={[dayGridPlugin, timeGridPlugin, classicThemePlugin]}
          locale={zhCnLocale}
          initialView="dayGridMonth"
          headerToolbar={{
            left: "prev,next today",
            center: "title",
            right: "dayGridMonth,timeGridWeek",
          }}
          height="auto"
          dayMaxEvents={3}
          nowIndicator
          events={events}
          eventTimeFormat={{ hour: "2-digit", minute: "2-digit", hour12: false }}
          datesSet={(info) => {
            // 只有范围真的变了才更新，避免重复请求
            setRange((prev) =>
              prev &&
              prev.start.getTime() === info.start.getTime() &&
              prev.end.getTime() === info.end.getTime()
                ? prev
                : { start: info.start, end: info.end },
            );
          }}
          eventClick={(info) => {
            info.jsEvent.preventDefault();
            router.push(`/applications/${info.event.extendedProps.applicationId}`);
          }}
          eventDidMount={(info) => {
            info.el.title = `${EVENT_TYPE_LABEL[info.event.extendedProps.type as keyof typeof EVENT_TYPE_LABEL]}：${info.event.title}`;
          }}
        />
      </div>
    </div>
  );
}
