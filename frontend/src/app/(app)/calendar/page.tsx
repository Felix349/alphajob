import type { Metadata } from "next";
import { Suspense } from "react";

import { CalendarView } from "@/components/calendar/calendar-view";
import { Skeleton } from "@/components/ui/skeleton";

export const metadata: Metadata = { title: "日历 · AlphaJob" };

export default function CalendarPage() {
  // 日历组件渲染时要读取“今天”（new Date()），这个值不能在构建时预渲染，所以包在 Suspense 里
  return (
    <Suspense fallback={<Skeleton className="mx-auto h-[600px] w-full max-w-6xl rounded-xl" />}>
      <CalendarView />
    </Suspense>
  );
}
