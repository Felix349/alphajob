"use client";

import { AlertTriangle, Check, Copy, Loader2, RefreshCw, Sparkles, Square } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { NativeSelect } from "@/components/ui/native-select";
import { Textarea } from "@/components/ui/textarea";
import { useMatchReport, useMatchStream } from "@/hooks/use-match";
import { useResume } from "@/hooks/use-resume";
import type { ApplicationDetail } from "@/lib/api/applications";
import type { MatchAnalysis, RequirementMatch, ResumeEdit } from "@/lib/api/match";
import type { ResumeLanguage } from "@/lib/api/resume";
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

type ResumeChoice = "auto" | ResumeLanguage;

// 匹配度规则：与后端 schemas/match.py 的 LEVEL_POINTS / IMPORTANCE_WEIGHT 保持一致
const POINTS: Record<RequirementMatch["level"], number> = { strong: 100, partial: 50, missing: 0 };
const IMPORTANCE: Record<RequirementMatch["importance"], { label: string; weight: number }> = {
  required: { label: "必备", weight: 2 },
  preferred: { label: "加分项", weight: 1 },
};

export function MatchPanel({ app }: { app: ApplicationDetail }) {
  const { data: report, isPending } = useMatchReport(app.id);
  const { data: zhResume } = useResume("zh");
  const { data: enResume } = useResume("en");
  const { state, start, cancel } = useMatchStream(app.id);
  const [notes, setNotes] = useState("");
  const [showNotes, setShowNotes] = useState(false);
  const [choice, setChoice] = useState<ResumeChoice>("auto");

  const streaming = state.status === "streaming";
  // 生成中显示正在生成的半成品，否则显示已保存的最新结果
  const analysis: Partial<MatchAnalysis> | undefined = streaming ? state.partial : report?.report;
  const hasJd = Boolean(app.jd_text || app.jd_parsed);
  const has: Record<ResumeLanguage, boolean> = { zh: Boolean(zhResume), en: Boolean(enResume) };
  // 选中的那份简历被删掉了，就退回“自动”
  const effectiveChoice: ResumeChoice = choice !== "auto" && !has[choice] ? "auto" : choice;
  const blocked = !has.zh && !has.en ? "no-resume" : !hasJd ? "no-jd" : null;

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
            onClick={() =>
              start({
                notes: notes.trim() || null,
                resume_language: effectiveChoice === "auto" ? null : effectiveChoice,
              })
            }
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
          <div className="flex flex-col gap-3">
            <label className="flex items-center gap-2 text-xs text-muted-foreground">
              使用的简历
              <NativeSelect
                aria-label="使用的简历"
                className="h-7 w-auto"
                value={effectiveChoice}
                onChange={(e) => setChoice(e.target.value as ResumeChoice)}
              >
                <option value="auto">自动（按 JD 语言）</option>
                <option value="zh" disabled={!has.zh}>
                  中文简历{has.zh ? "" : "（未上传）"}
                </option>
                <option value="en" disabled={!has.en}>
                  英文简历{has.en ? "" : "（未上传）"}
                </option>
              </NativeSelect>
            </label>
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
          </div>
        )}

        {report?.stale && !streaming && (
          <Hint tone="warn">
            这次分析用的{report.resume_language === "en" ? "英文" : "中文"}
            简历之后又更新过，建议重新分析。
          </Hint>
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
            {new Date(report.created_at).toLocaleString("zh-CN")} · 基于
            {report.resume_language === "en" ? "英文" : "中文"}简历 · {report.model}
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
      {/* 分数只在生成完成后出现（由后端按规则计算），这时再展示计算过程 */}
      {analysis.score !== undefined && analysis.requirements && (
        <ScoreRule requirements={analysis.requirements} score={analysis.score} />
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
                    <div className="flex shrink-0 gap-1.5">
                      {r.importance && (
                        <Badge variant="outline">{IMPORTANCE[r.importance].label}</Badge>
                      )}
                      <Badge className={cn("border-0", LEVEL[r.level].className)}>
                        {LEVEL[r.level].label}
                      </Badge>
                    </div>
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

      {analysis.resume_edits && analysis.resume_edits.length > 0 && (
        <Section title="简历修改建议">
          <p className="mb-2 text-xs text-muted-foreground">
            只调整写法、不添加新经历；【待补充】的地方请换成你自己的真实数据，再到“我的简历”里替换。
          </p>
          <ul className="flex flex-col gap-2">
            {analysis.resume_edits.map((e, i) =>
              // 流式生成时最后一项可能还不完整，等 suggestion 出来再显示
              e?.section && e.suggestion ? <ResumeEditItem key={i} edit={e} /> : null,
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

function ResumeEditItem({ edit }: { edit: ResumeEdit }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(edit.suggestion);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      toast.error("复制失败，请手动选中文字复制");
    }
  }

  return (
    <li className="rounded-lg border p-3">
      <div className="flex items-start justify-between gap-3">
        <span className="font-medium">{edit.section}</span>
        <Badge variant="outline" className="shrink-0">
          {edit.original ? "改写" : "新增"}
        </Badge>
      </div>
      {edit.original && (
        <p className="mt-2 text-muted-foreground line-through decoration-muted-foreground/40">
          {edit.original}
        </p>
      )}
      <div className="mt-1.5 flex items-start gap-2 rounded-md bg-emerald-50 p-2 dark:bg-emerald-950/40">
        <p className="flex-1 whitespace-pre-wrap">{edit.suggestion}</p>
        <Button
          variant="ghost"
          size="icon"
          className="size-6 shrink-0"
          aria-label="复制修改后的写法"
          onClick={copy}
        >
          {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
        </Button>
      </div>
      {edit.reason && (
        <p className="mt-1.5 text-muted-foreground">
          <span className="text-foreground/70">理由：</span>
          {edit.reason}
        </p>
      )}
    </li>
  );
}

/**
 * 匹配度的计算过程。规则和后端 schemas/match.py 的 compute_score 一致，改动时两边同步。
 * 分数本身用后端返回的值，这里只负责把“怎么算出来的”摆出来。
 */
function ScoreRule({ requirements, score }: { requirements: RequirementMatch[]; score: number }) {
  const rows = (Object.keys(IMPORTANCE) as RequirementMatch["importance"][])
    .map((importance) => {
      const items = requirements.filter((r) => r.importance === importance);
      const count = (level: RequirementMatch["level"]) =>
        items.filter((r) => r.level === level).length;
      return {
        importance,
        items,
        strong: count("strong"),
        partial: count("partial"),
        missing: count("missing"),
      };
    })
    .filter((row) => row.items.length > 0);
  const totalWeight = rows.reduce(
    (s, r) => s + r.items.length * IMPORTANCE[r.importance].weight,
    0,
  );
  const totalPoints = rows.reduce(
    (s, r) =>
      s + IMPORTANCE[r.importance].weight * (r.strong * POINTS.strong + r.partial * POINTS.partial),
    0,
  );

  return (
    <details className="group rounded-lg border px-3 py-2 text-xs text-muted-foreground">
      <summary className="cursor-pointer select-none text-foreground/80">
        匹配度是怎么算的？
      </summary>
      <div className="mt-2 flex flex-col gap-2 leading-relaxed">
        <p>
          匹配度不是 AI
          凭印象打的分，而是根据下方“逐条对照”的结果按固定规则计算：每条要求按匹配程度得分（
          <b>
            匹配 {POINTS.strong} 分、部分匹配 {POINTS.partial} 分、缺失 {POINTS.missing} 分
          </b>
          ），再按重要程度加权平均（
          <b>
            必备要求权重 {IMPORTANCE.required.weight}，加分项权重 {IMPORTANCE.preferred.weight}
          </b>
          ）。AI 只负责判断每条要求的匹配程度和是否必备。
        </p>
        {rows.length > 0 && (
          <table className="w-full text-left tabular-nums">
            <thead>
              <tr className="border-b">
                <th className="py-1 font-normal">类别</th>
                <th className="py-1 font-normal">匹配</th>
                <th className="py-1 font-normal">部分匹配</th>
                <th className="py-1 font-normal">缺失</th>
                <th className="py-1 font-normal">权重</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.importance} className="border-b last:border-0">
                  <td className="py-1">{IMPORTANCE[r.importance].label}</td>
                  <td className="py-1">{r.strong}</td>
                  <td className="py-1">{r.partial}</td>
                  <td className="py-1">{r.missing}</td>
                  <td className="py-1">×{IMPORTANCE[r.importance].weight}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {totalWeight > 0 && (
          <p>
            加权得分 {totalPoints} ÷ 总权重 {totalWeight} ≈{" "}
            <b className="text-foreground">{score}</b>（四舍五入）
          </p>
        )}
      </div>
    </details>
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
