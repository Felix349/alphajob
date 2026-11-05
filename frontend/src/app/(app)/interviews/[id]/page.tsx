import type { Metadata } from "next";
import { Suspense } from "react";

import { InterviewDetailView } from "@/components/interviews/interview-detail-view";
import { Skeleton } from "@/components/ui/skeleton";

export const metadata: Metadata = { title: "面试复盘 · AlphaJob" };

export default function InterviewPage() {
  // 详情视图通过 useParams() 读取 id，只有运行时才知道，所以包在 Suspense 里
  return (
    <Suspense fallback={<Skeleton className="h-96 w-full max-w-4xl rounded-xl" />}>
      <InterviewDetailView />
    </Suspense>
  );
}
