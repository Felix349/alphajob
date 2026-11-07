import type { Metadata } from "next";

import { ChatPanel } from "@/components/agent/chat-panel";
import { PlanCard } from "@/components/agent/plan-cards";

export const metadata: Metadata = { title: "求职 Agent · AlphaJob" };

export default function AgentPage() {
  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">求职 Agent</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          它能看到你的投递、日程、备考清单和复盘结果，帮你安排每天该做什么；修改数据前都会先请你确认。
        </p>
      </div>
      <div className="grid gap-6 lg:grid-cols-[1fr_420px]">
        <PlanCard />
        <ChatPanel />
      </div>
    </div>
  );
}
