import type { Metadata } from "next";

import { ScreeningView } from "@/components/screening/screening-view";

export const metadata: Metadata = { title: "岗位筛选 · AlphaJob" };

export default function ScreeningPage() {
  return <ScreeningView />;
}
