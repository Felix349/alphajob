"use client";

import { Loader2, Mic, RotateCw, Type } from "lucide-react";
import Link from "next/link";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useRetryInterview } from "@/hooks/use-interviews";
import { IN_PROGRESS, type Interview } from "@/lib/api/interviews";
import { formatDate } from "@/lib/format";
import { STATUS } from "@/lib/interview-meta";
import { cn } from "@/lib/utils";

export function InterviewRow({ interview, title }: { interview: Interview; title?: string }) {
  const retry = useRetryInterview();
  const busy = IN_PROGRESS.includes(interview.status);
  const s = STATUS[interview.status];

  return (
    <li className="flex items-start gap-3 rounded-lg border p-3 transition-colors hover:bg-muted/40">
      <span className="mt-0.5 text-muted-foreground">
        {interview.input_type === "audio" ? (
          <Mic className="size-4" />
        ) : (
          <Type className="size-4" />
        )}
      </span>
      <Link href={`/interviews/${interview.id}`} className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="truncate font-medium">{title ?? interview.round}</span>
          <Badge className={cn("shrink-0 border-0", s.className)}>
            {busy && <Loader2 className="size-3 animate-spin" />}
            {s.label}
          </Badge>
        </div>
        <div className="mt-0.5 text-xs text-muted-foreground">
          {interview.held_on ? formatDate(interview.held_on) : "日期未填"}
          {interview.status === "done" && ` · ${interview.question_count} 道题`}
        </div>
        {interview.status === "failed" && interview.error && (
          <p className="mt-1 text-xs text-destructive">{interview.error}</p>
        )}
      </Link>
      {interview.status === "failed" && (
        <Button
          size="sm"
          variant="outline"
          disabled={retry.isPending}
          onClick={() => retry.mutate(interview.id, { onError: (e) => toast.error(e.message) })}
        >
          <RotateCw className="size-3.5" />
          重试
        </Button>
      )}
    </li>
  );
}
