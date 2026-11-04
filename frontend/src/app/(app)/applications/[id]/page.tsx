import type { Metadata } from "next";
import { Suspense } from "react";

import { ApplicationDetailView } from "@/components/applications/application-detail-view";
import { Skeleton } from "@/components/ui/skeleton";

export const metadata: Metadata = { title: "投递详情 · AlphaJob" };

export default function ApplicationPage() {
  // 详情视图通过 useParams() 读取 id，只有运行时才知道，所以包在 Suspense 里
  return (
    <Suspense fallback={<Skeleton className="h-96 w-full max-w-5xl rounded-xl" />}>
      <ApplicationDetailView />
    </Suspense>
  );
}
