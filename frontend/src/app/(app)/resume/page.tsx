import type { Metadata } from "next";

import { ResumeView } from "@/components/resume/resume-view";

export const metadata: Metadata = { title: "我的简历 · AlphaJob" };

export default function ResumePage() {
  return <ResumeView />;
}
