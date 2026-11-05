"use client";

import { Plus } from "lucide-react";
import { useState } from "react";

import { NewInterviewDialog } from "@/components/interviews/new-interview-dialog";
import { InterviewRow } from "@/components/interviews/interview-row";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useApplicationInterviews } from "@/hooks/use-interviews";
import { suggestRound } from "@/lib/interview-meta";

export function InterviewPanel({ appId }: { appId: string }) {
  const { data: interviews = [] } = useApplicationInterviews(appId);
  const [open, setOpen] = useState(false);

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>面试复盘</CardTitle>
        <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
          <Plus className="size-4" />
          复盘
        </Button>
      </CardHeader>
      <CardContent className="text-sm">
        {interviews.length === 0 ? (
          <p className="text-muted-foreground">
            面试结束后，口述或写下回忆，AI 帮你整理成复盘和题库。
          </p>
        ) : (
          <ul className="flex flex-col gap-2">
            {interviews.map((iv) => (
              <InterviewRow key={iv.id} interview={iv} />
            ))}
          </ul>
        )}
      </CardContent>
      {/* key：每次打开都用最新的建议轮次重新初始化表单 */}
      {open && (
        <NewInterviewDialog
          key={interviews.length}
          appId={appId}
          defaultRound={suggestRound(interviews.length)}
          open={open}
          onOpenChange={setOpen}
        />
      )}
    </Card>
  );
}
