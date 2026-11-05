"use client";

import { ArrowLeft, Check, ChevronDown, Loader2, RotateCw, Trash2, X } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { NativeSelect } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useDeleteInterview,
  useInterview,
  useRetryInterview,
  useUpdateMastery,
} from "@/hooks/use-interviews";
import { ApiError } from "@/lib/api/client";
import type { InterviewDetail, Mastery, Question } from "@/lib/api/interviews";
import { formatDate } from "@/lib/format";
import { MASTERY, SCORE_LABEL, formatDuration, scoreClass } from "@/lib/interview-meta";
import { cn } from "@/lib/utils";

export function InterviewDetailView() {
  const { id } = useParams<{ id: string }>();
  const { data, isPending, error } = useInterview(id);

  if (isPending) return <Skeleton className="h-96 w-full max-w-4xl rounded-xl" />;
  if (error) {
    const notFound = error instanceof ApiError && error.status === 404;
    return (
      <div className="mx-auto max-w-md py-16 text-center">
        <p className="font-medium">{notFound ? "复盘记录不存在" : `加载失败：${error.message}`}</p>
        <Link href="/interviews" className="mt-4 inline-block text-sm underline">
          返回复盘列表
        </Link>
      </div>
    );
  }
  return <Detail interview={data} />;
}

function Detail({ interview }: { interview: InterviewDetail }) {
  const router = useRouter();
  const retry = useRetryInterview();
  const remove = useDeleteInterview();

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6">
      <div>
        <Link
          href={`/applications/${interview.application_id}`}
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="size-4" />
          {interview.company} · {interview.role}
        </Link>
        <div className="mt-3 flex items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">{interview.round}复盘</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              {interview.held_on ? formatDate(interview.held_on) : "日期未填"}
              {interview.input_type === "audio" && interview.audio_seconds
                ? ` · 录音 ${formatDuration(interview.audio_seconds)}`
                : ""}
              {interview.model && ` · ${interview.model}`}
            </p>
          </div>
          <Button
            variant="ghost"
            size="icon"
            aria-label="删除复盘"
            onClick={() => {
              if (!window.confirm("删除这次复盘？整理出的题目也会一起从题库中删除。")) return;
              remove.mutate(interview.id, {
                onSuccess: () => router.replace(`/applications/${interview.application_id}`),
                onError: (e) => toast.error(e.message),
              });
            }}
          >
            <Trash2 className="size-4" />
          </Button>
        </div>
      </div>

      {interview.status !== "done" && (
        <Progress
          interview={interview}
          onRetry={() => retry.mutate(interview.id, { onError: (e) => toast.error(e.message) })}
          retrying={retry.isPending}
        />
      )}

      {interview.summary && (
        <Card>
          <CardHeader>
            <CardTitle>总结</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-4 text-sm">
            <p className="leading-relaxed">{interview.summary.summary}</p>
            <div className="grid gap-4 sm:grid-cols-2">
              <Bullets title="表现好的地方" items={interview.summary.highlights} />
              <div>
                <h3 className="mb-1.5 font-medium">薄弱点</h3>
                {interview.summary.weak_points.length === 0 ? (
                  <p className="text-muted-foreground">无</p>
                ) : (
                  <ul className="space-y-1.5">
                    {interview.summary.weak_points.map((w, i) => (
                      <li key={i}>
                        <span className="font-medium text-rose-700 dark:text-rose-300">
                          {w.topic}
                        </span>
                        <span className="text-muted-foreground">：{w.detail}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
            <Bullets title="下一轮怎么准备" items={interview.summary.next_round_advice} ordered />
          </CardContent>
        </Card>
      )}

      {interview.questions.length > 0 && (
        <section className="flex flex-col gap-3">
          <h2 className="text-lg font-semibold">逐题复盘（{interview.questions.length}）</h2>
          {interview.questions.map((q, i) => (
            <QuestionCard key={q.id} index={i + 1} question={q} />
          ))}
        </section>
      )}

      {(interview.transcript || interview.raw_text) && (
        <details className="rounded-xl border p-4 text-sm">
          <summary className="cursor-pointer font-medium">
            {interview.input_type === "audio" ? "语音转写原文" : "你写的回忆原文"}
          </summary>
          <p className="mt-3 leading-relaxed whitespace-pre-wrap text-muted-foreground">
            {interview.transcript ?? interview.raw_text}
          </p>
        </details>
      )}
    </div>
  );
}

const STEPS = [
  { key: "transcribing", label: "语音转写" },
  { key: "analyzing", label: "整理与评估" },
  { key: "done", label: "完成" },
] as const;

function Progress({
  interview,
  onRetry,
  retrying,
}: {
  interview: InterviewDetail;
  onRetry: () => void;
  retrying: boolean;
}) {
  // 文字输入没有“转写”这一步
  const steps = interview.input_type === "audio" ? STEPS : STEPS.slice(1);
  const failed = interview.status === "failed";
  // 失败时，根据有没有转写结果判断卡在了哪一步
  const current = failed
    ? interview.input_type === "audio" && !interview.transcript
      ? "transcribing"
      : "analyzing"
    : interview.status === "pending"
      ? steps[0].key
      : interview.status;
  const currentIndex = steps.findIndex((s) => s.key === current);

  return (
    <Card>
      <CardContent className="flex flex-col gap-4 pt-6">
        <ol className="flex items-center gap-2 text-sm">
          {steps.map((step, i) => {
            const done = i < currentIndex;
            const active = i === currentIndex;
            return (
              <li key={step.key} className="flex flex-1 items-center gap-2">
                <span
                  className={cn(
                    "flex size-6 shrink-0 items-center justify-center rounded-full border text-xs",
                    done && "border-emerald-500 bg-emerald-500 text-white",
                    active && !failed && "border-primary text-primary",
                    active && failed && "border-rose-500 bg-rose-500 text-white",
                  )}
                >
                  {done ? (
                    <Check className="size-3.5" />
                  ) : active && failed ? (
                    <X className="size-3.5" />
                  ) : active ? (
                    <Loader2 className="size-3.5 animate-spin" />
                  ) : (
                    i + 1
                  )}
                </span>
                <span className={cn(!done && !active && "text-muted-foreground")}>
                  {step.label}
                </span>
                {i < steps.length - 1 && <span className="h-px flex-1 bg-border" />}
              </li>
            );
          })}
        </ol>
        {failed ? (
          <div className="flex items-center justify-between gap-4 rounded-lg bg-rose-50 p-3 text-sm text-rose-900 dark:bg-rose-950/40 dark:text-rose-100">
            <span>{interview.error}</span>
            <Button size="sm" variant="outline" onClick={onRetry} disabled={retrying}>
              <RotateCw className="size-3.5" />
              重试
            </Button>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            {interview.status === "pending" ? "排队中…" : "处理中…"}
            可以先离开这个页面，处理完成后结果会自动保存。
          </p>
        )}
      </CardContent>
    </Card>
  );
}

export function QuestionCard({
  question,
  index,
  meta,
}: {
  question: Question;
  index?: number;
  meta?: React.ReactNode;
}) {
  const update = useUpdateMastery();
  return (
    <Card>
      <CardContent className="flex flex-col gap-3 pt-6 text-sm">
        <div className="flex items-start justify-between gap-3">
          <h3 className="font-medium leading-relaxed">
            {index !== undefined && <span className="mr-1.5 text-muted-foreground">{index}.</span>}
            {question.question}
          </h3>
          <Badge className={cn("shrink-0 border-0", scoreClass(question.score))}>
            {question.score} 分 · {SCORE_LABEL[question.score]}
          </Badge>
        </div>
        {meta}
        <div className="rounded-lg bg-muted/50 p-3">
          <span className="text-xs text-muted-foreground">你当时的回答</span>
          <p className="mt-1">{question.my_answer ?? "（回忆里没有提到）"}</p>
        </div>
        <p>
          <span className="text-muted-foreground">点评：</span>
          {question.feedback}
        </p>
        <details className="group rounded-lg border p-3">
          <summary className="flex cursor-pointer list-none items-center gap-1 font-medium">
            <ChevronDown className="size-4 transition-transform group-open:rotate-180" />
            参考回答
          </summary>
          <p className="mt-2 leading-relaxed whitespace-pre-wrap">{question.improved_answer}</p>
        </details>
        <div className="flex items-center justify-between gap-3">
          <div className="flex flex-wrap gap-1">
            {question.tags.map((t) => (
              <Badge key={t} variant="secondary">
                {t}
              </Badge>
            ))}
          </div>
          <NativeSelect
            aria-label="掌握程度"
            value={question.mastery}
            className="h-7 w-24 text-xs"
            onChange={(e) =>
              update.mutate(
                { id: question.id, mastery: e.target.value as Mastery },
                { onError: (err) => toast.error(err.message) },
              )
            }
          >
            {Object.entries(MASTERY).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </NativeSelect>
        </div>
      </CardContent>
    </Card>
  );
}

function Bullets({ title, items, ordered }: { title: string; items: string[]; ordered?: boolean }) {
  const List = ordered ? "ol" : "ul";
  return (
    <div>
      <h3 className="mb-1.5 font-medium">{title}</h3>
      {items.length === 0 ? (
        <p className="text-muted-foreground">无</p>
      ) : (
        <List className={cn("space-y-1 pl-5", ordered ? "list-decimal" : "list-disc")}>
          {items.map((t, i) => (
            <li key={i}>{t}</li>
          ))}
        </List>
      )}
    </div>
  );
}
