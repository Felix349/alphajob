"use client";

import { Check, ChevronDown, ExternalLink, Plus } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useImportJob, useSetJd } from "@/hooks/use-screening";
import { type ScreeningJob, rankResultOf } from "@/lib/api/screening";
import { cn } from "@/lib/utils";

const LEVEL = {
  strong: {
    label: "匹配",
    className: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200",
  },
  partial: {
    label: "部分",
    className: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-200",
  },
  missing: {
    label: "缺失",
    className: "bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-200",
  },
} as const; // fmt: skip

export function scoreColor(score: number) {
  return score >= 75 ? "text-emerald-600" : score >= 50 ? "text-amber-600" : "text-rose-600";
}

function OpenLink({ url }: { url: string | null }) {
  if (!url) return null;
  return (
    <a
      href={url}
      target="_blank"
      rel="noreferrer"
      className="inline-flex shrink-0 items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
    >
      <ExternalLink className="size-3.5" />
      原页面
    </a>
  );
}

function Meta({ job }: { job: ScreeningJob }) {
  const parts = [job.location, job.category, job.job_type].filter(Boolean);
  return parts.length > 0 ? (
    <span className="text-xs text-muted-foreground">{parts.join(" · ")}</span>
  ) : null;
}

/** 推荐清单里的一项：匹配度、优势、差距，可展开逐条对照，可加入投递记录。 */
export function RankedJobCard({
  batchId,
  job,
  rank,
}: {
  batchId: string;
  job: ScreeningJob;
  rank: number;
}) {
  const result = rankResultOf(job);
  const [expanded, setExpanded] = useState(false);

  return (
    <li className="rounded-lg border p-4">
      <div className="flex items-start gap-4">
        <div className="flex w-12 shrink-0 flex-col items-center">
          <span className="text-xs text-muted-foreground">#{rank}</span>
          {job.score !== null ? (
            <span className={cn("text-2xl font-semibold tabular-nums", scoreColor(job.score))}>
              {job.score}
            </span>
          ) : (
            <span className="text-sm text-muted-foreground">—</span>
          )}
        </div>
        <div className="min-w-0 flex-1">
          {/* 按钮和标题同一行、空间不够时换到下一行；不单独占一列，窄屏时正文也有足够宽度 */}
          <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
            <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1">
              <span className="font-medium">{job.title}</span>
              <Meta job={job} />
              <OpenLink url={job.url} />
            </div>
            <ImportButton batchId={batchId} job={job} />
          </div>
          {result && (
            <div className="mt-2 flex flex-col gap-1 text-sm">
              <p>
                <span className="text-muted-foreground">优势：</span>
                {result.strength}
              </p>
              <p>
                <span className="text-muted-foreground">差距：</span>
                {result.gap}
              </p>
            </div>
          )}
          {job.rank_error && (
            <p className="mt-2 text-sm text-destructive">
              精排失败：{job.rank_error}（重新精排即可重试）
            </p>
          )}
          {result && (
            <button
              type="button"
              onClick={() => setExpanded((v) => !v)}
              className="mt-2 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
            >
              <ChevronDown
                className={cn("size-3.5 transition-transform", expanded && "rotate-180")}
              />
              {expanded ? "收起" : `逐条对照（${result.requirements.length} 条）`}
            </button>
          )}
          {expanded && result && (
            <ul className="mt-2 flex flex-col gap-1.5 text-sm">
              {result.requirements.map((r, i) => (
                <li key={i} className="flex items-start gap-2">
                  <Badge className={cn("shrink-0 border-0", LEVEL[r.level].className)}>
                    {LEVEL[r.level].label}
                  </Badge>
                  <span>
                    {r.requirement}
                    {r.importance === "preferred" && (
                      <span className="ml-1 text-xs text-muted-foreground">（加分项）</span>
                    )}
                    {r.evidence && (
                      <span className="block text-xs text-muted-foreground">
                        依据：{r.evidence}
                      </span>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </li>
  );
}

function ImportButton({ batchId, job }: { batchId: string; job: ScreeningJob }) {
  const importJob = useImportJob(batchId);
  if (job.application_id) {
    return (
      <Link
        href={`/applications/${job.application_id}`}
        className="inline-flex shrink-0 items-center gap-1 text-sm text-emerald-700 hover:underline dark:text-emerald-400"
      >
        <Check className="size-4" />
        已加入，查看
      </Link>
    );
  }
  return (
    <Button
      size="sm"
      variant="outline"
      className="shrink-0"
      disabled={importJob.isPending}
      onClick={() =>
        importJob.mutate(job.id, {
          onSuccess: () => toast.success(`已加入投递记录（想投）：${job.title}`),
          onError: (err) => toast.error(err.message),
        })
      }
    >
      <Plus className="size-4" />
      {importJob.isPending ? "加入中…" : "加入投递记录"}
    </Button>
  );
}

/** 进入精排、但还没有 JD 的岗位：打开原页面，把 JD 复制过来。P3 会由插件自动读取。 */
export function JdInputCard({ batchId, job }: { batchId: string; job: ScreeningJob }) {
  const [text, setText] = useState("");
  const setJd = useSetJd(batchId);
  const ready = text.trim().length >= 20;

  return (
    <li className="rounded-lg border p-3">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="font-medium">{job.title}</span>
        <Meta job={job} />
        <OpenLink url={job.url} />
        {job.coarse_reason && (
          <span className="text-xs text-muted-foreground">粗筛：{job.coarse_reason}</span>
        )}
      </div>
      <Textarea
        aria-label={`${job.title} 的 JD`}
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="打开原页面，把岗位职责和任职要求复制到这里"
        className="mt-2 min-h-24 text-sm"
      />
      <div className="mt-2 flex justify-end">
        <Button
          size="sm"
          disabled={!ready || setJd.isPending}
          onClick={() =>
            setJd.mutate(
              { jobId: job.id, jdText: text.trim() },
              { onError: (err) => toast.error(err.message) },
            )
          }
        >
          {setJd.isPending ? "保存中…" : "保存 JD"}
        </Button>
      </div>
    </li>
  );
}

/** 没进入精排的岗位：显示被过滤的原因，或粗筛的分数和理由，方便回看“为什么没选它”。 */
export function OtherJobRow({ job }: { job: ScreeningJob }) {
  return (
    <li className="flex items-baseline gap-3 py-1.5 text-sm">
      <span className="w-6 shrink-0 text-center text-xs tabular-nums text-muted-foreground">
        {job.filtered_reason ? "—" : (job.coarse_score ?? "?")}
      </span>
      <span className="min-w-0 flex-1">
        {job.title}
        <span className="ml-2 text-xs text-muted-foreground">
          {job.filtered_reason ? `已排除：${job.filtered_reason}` : job.coarse_reason}
        </span>
      </span>
      <OpenLink url={job.url} />
    </li>
  );
}
