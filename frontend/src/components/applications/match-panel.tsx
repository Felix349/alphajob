"use client";

import { AlertTriangle, Loader2, RefreshCw, Sparkles, Square } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { useMatchReport, useMatchStream } from "@/hooks/use-match";
import { useResume } from "@/hooks/use-resume";
import type { ApplicationDetail } from "@/lib/api/applications";
import type { MatchAnalysis, RequirementMatch } from "@/lib/api/match";
import { cn } from "@/lib/utils";

const LEVEL: Record<RequirementMatch["level"], { label: string; className: string }> = {
  strong: {
    label: "匹配",
    className: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200",
  },
  partial: {
    label: "部分匹配",
    className: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-200",
  },
  missing: {
    label: "缺失",
    className: "bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-200",
  },
};

export function MatchPanel({ app }: { app: ApplicationDetail }) {
  const { data: report, isPending } = useMatchReport(app.id);
  const { data: resume } = useResume();
  const { state, start, cancel } = useMatchStream(app.id);
  const [notes, setNotes] = useState("");
  const [showNotes, setShowNotes] = useState(false);

  const streaming = state.status === "streaming";
  // 生成中显示正在生成的半成品，否则显示已保存的最新结果
  const analysis: Partial<MatchAnalysis> | undefined = streaming ? state.partial : report?.report;
  const hasJd = Boolean(app.jd_text || app.jd_parsed);
  const blocked = !resume ? "no-resume" : !hasJd ? "no-jd" : null;

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-4">
        <div>
          <CardTitle>岗位匹配</CardTitle>
          <CardDescription className="mt-1">
            对照 JD 和你的简历，找出亮点与差距，并生成备考清单
          </CardDescription>
        </div>
        {streaming ? (
          <Button variant="outline" size="sm" onClick={cancel}>
            <Square className="size-3.5" />
            停止
          </Button>
        ) : (
          <Button
            size="sm"
            disabled={Boolean(blocked) || isPending}
            onClick={() => start(notes.trim() || null)}
          >
            {report ? <RefreshCw className="size-4" /> : <Sparkles className="size-4" />}
            {report ? "重新分析" : "生成分析"}
          </Button>
        )}
      </CardHeader>

      <CardContent className="flex flex-col gap-5 text-sm">
        {blocked === "no-resume" && (
          <Hint>
            还没有简历。先到{" "}
            <Link href="/resume" className="font-medium underline">
              我的简历
            </Link>{" "}
            上传，再回来分析。
          </Hint>
        )}
        {blocked === "no-jd" && <Hint>这条投递还没有岗位描述，先在下方“岗位描述”里补充 JD。</Hint>}

        {!blocked && !streaming && (
          <div>
            <button
              type="button"
              className="text-xs text-muted-foreground underline-offset-4 hover:underline"
              onClick={() => setShowNotes((v) => !v)}
            >
              {showNotes ? "收起补充信息" : "+ 补充面经或内推信息（可选）"}
            </button>
            {showNotes && (
              <Textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="例如：一面问了 Transformer 的注意力计算、手写 LRU；面试官很看重项目里的数据量级……"
                className="mt-2 min-h-24"
              />
            )}
          </div>
        )}

        {report?.stale && !streaming && (
          <Hint tone="warn">简历在这次分析之后更新过，建议重新分析。</Hint>
        )}
        {state.status === "error" && <Hint tone="error">{state.message}</Hint>}
        {streaming && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Loader2 className="size-3.5 animate-spin" />
            {state.note ?? "正在分析"}…已生成 {state.chars} 字
          </div>
        )}

        {analysis && <AnalysisView analysis={analysis} />}

        {!analysis && !streaming && !blocked && !isPending && (
          <p className="text-muted-foreground">
            还没有分析结果。点击“生成分析”，大约需要 20–40 秒。
          </p>
        )}
        {report && !streaming && (
          <p className="text-xs text-muted-foreground">
            {new Date(report.created_at).toLocaleString("zh-CN")} · {report.model}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function AnalysisView({ analysis }: { analysis: Partial<MatchAnalysis> }) {
  return (
    <div className="flex flex-col gap-5">
      {(analysis.score !== undefined || analysis.summary) && (
        <div className="flex items-start gap-4 rounded-lg bg-muted/50 p-4">
          {analysis.score !== undefined && <Score value={analysis.score} />}
          {analysis.summary && <p className="leading-relaxed">{analysis.summary}</p>}
        </div>
      )}

      {analysis.highlights && analysis.highlights.length > 0 && (
        <Section title="面试重点讲">
          <ul className="list-disc space-y-1 pl-5">
            {analysis.highlights.map((h, i) => (
              <li key={i}>{h}</li>
            ))}
          </ul>
        </Section>
      )}

      {analysis.requirements && analysis.requirements.length > 0 && (
        <Section title="逐条对照">
          <ul className="flex flex-col gap-2">
            {analysis.requirements.map((r, i) =>
              // 流式生成时最后一项可能还不完整，等它有了 level 再显示
              r?.requirement && r.level ? (
                <li key={i} className="rounded-lg border p-3">
                  <div className="flex items-start justify-between gap-3">
                    <span className="font-medium">{r.requirement}</span>
                    <Badge className={cn("shrink-0 border-0", LEVEL[r.level].className)}>
                      {LEVEL[r.level].label}
                    </Badge>
                  </div>
                  {r.evidence && (
                    <p className="mt-1.5 text-muted-foreground">
                      <span className="text-foreground/70">依据：</span>
                      {r.evidence}
                    </p>
                  )}
                  {r.advice && (
                    <p className="mt-1 text-muted-foreground">
                      <span className="text-foreground/70">建议：</span>
                      {r.advice}
                    </p>
                  )}
                </li>
              ) : null,
            )}
          </ul>
        </Section>
      )}

      {analysis.interview_questions && analysis.interview_questions.length > 0 && (
        <Section title="可能被问到">
          <ol className="list-decimal space-y-1 pl-5">
            {analysis.interview_questions.map((q, i) => (
              <li key={i}>{q}</li>
            ))}
          </ol>
        </Section>
      )}
    </div>
  );
}

function Score({ value }: { value: number }) {
  const color = value >= 75 ? "text-emerald-600" : value >= 50 ? "text-amber-600" : "text-rose-600";
  return (
    <div className="flex shrink-0 flex-col items-center">
      <span className={cn("text-3xl font-semibold tabular-nums", color)}>{value}</span>
      <span className="text-xs text-muted-foreground">匹配度</span>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h3 className="mb-2 font-medium">{title}</h3>
      {children}
    </section>
  );
}

function Hint({
  children,
  tone = "info",
}: {
  children: React.ReactNode;
  tone?: "info" | "warn" | "error";
}) {
  return (
    <div
      className={cn(
        "flex items-start gap-2 rounded-lg border p-3",
        tone === "warn" &&
          "border-amber-300 bg-amber-50 text-amber-900 dark:bg-amber-950/40 dark:text-amber-100",
        tone === "error" &&
          "border-rose-300 bg-rose-50 text-rose-900 dark:bg-rose-950/40 dark:text-rose-100",
        tone === "info" && "bg-muted/40 text-muted-foreground",
      )}
    >
      {tone !== "info" && <AlertTriangle className="mt-0.5 size-4 shrink-0" />}
      <div>{children}</div>
    </div>
  );
}
