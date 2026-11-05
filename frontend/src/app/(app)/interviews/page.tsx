import type { Metadata } from "next";

import { InterviewsView } from "@/components/interviews/interviews-view";

export const metadata: Metadata = { title: "面试复盘 · AlphaJob" };

export default function InterviewsPage() {
  return <InterviewsView />;
}
