"use client";

import { ArrowLeft, Filter, Loader2, Sparkles, Trash2 } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import {
  useBatch,
  useDeleteBatch,
  useExtractJobs,
  useRank,
  useScreen,
} from "@/hooks/use-screening";
import type { BatchDetail } from "@/lib/api/screening";

import { JdInputCard, OtherJobRow, RankedJobCard } from "./job-cards";
import { BATCH_STATUS } from "./screening-view";

export function BatchView() {
  const { id } = useParams<{ id: string }>();
  const { data: batch, isPending, error } = useBatch(id);

  if (isPending) return <Skeleton className="mx-auto h-96 w-full max-w-4xl rounded-xl" />;
  if (error) return <p className="text-sm text-destructive">加载失败：{error.message}</p>;
  return <BatchContent batch={batch} />;
}

function BatchContent({ batch }: { batch: BatchDetail }) {
  const router = useRouter();
  const remove = useDeleteBatch();
  const jobs = batch.jobs; // 后端已按推荐顺序排好
  const shortlisted = jobs.filter((j) => j.shortlisted);
  const ranked = shortlisted.filter((j) => j.score !== null || j.rank_error);
  const needsJd = shortlisted.filter((j) => !j.has_jd);
  const waiting = shortlisted.filter((j) => j.has_jd && j.score === null && !j.rank_error);
  const others = jobs.filter((j) => !j.shortlisted);
  const screened = jobs.some((j) => j.coarse_score !== null || j.filtered_reason);

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6">
      <div>
        <Link
          href="/screening"
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="size-4" />
          岗位筛选
        </Link>
        <div className="mt-2 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-semibold tracking-tight">{batch.company}</h1>
            <Badge variant="outline">{BATCH_STATUS[batch.status] ?? batch.status}</Badge>
          </div>
          <Button
            variant="ghost"
            size="icon"
            aria-label="删除这次筛选"
            disabled={remove.isPending}
            onClick={() => {
              if (!window.confirm("删除这次筛选吗？已加入投递记录的岗位不受影响。")) return;
              remove.mutate(batch.id, {
                onSuccess: () => router.replace("/screening"),
                onError: (err) => toast.error(err.message),
              });
            }}
          >
            <Trash2 className="size-4" />
          </Button>
        </div>
        <p className="mt-1 text-sm text-muted-foreground">
          {batch.total_jobs} 个岗位 · 精排前 {batch.top_n} 个
          {batch.filters.cities?.length ? ` · 城市：${batch.filters.cities.join("、")}` : ""}
          {batch.filters.job_types?.length ? ` · ${batch.filters.job_types.join("、")}` : ""}
        </p>
      </div>

      <CollectStep batch={batch} />
      {jobs.length > 0 && <ScreenStep batch={batch} screened={screened} />}

      {needsJd.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>补充 JD</CardTitle>
            <CardDescription>
              精排要读完整的岗位描述。还有 {needsJd.length} 个入选岗位缺
              JD：打开原页面复制过来；没补的岗位不参与精排。之后浏览器插件会自动完成这一步。
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="flex flex-col gap-3">
              {needsJd.map((j) => (
                <JdInputCard key={j.id} batchId={batch.id} job={j} />
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {shortlisted.some((j) => j.has_jd) && (
        <RankStep batchId={batch.id} pending={waiting.length} hasResults={ranked.length > 0} />
      )}

      {ranked.length > 0 && (
        <section>
          <h2 className="mb-3 text-lg font-semibold">推荐清单</h2>
          <ul className="flex flex-col gap-3">
            {ranked.map((j, i) => (
              <RankedJobCard key={j.id} batchId={batch.id} job={j} rank={i + 1} />
            ))}
          </ul>
        </section>
      )}

      {screened && others.length > 0 && (
        <details className="rounded-lg border px-4 py-3">
          <summary className="cursor-pointer text-sm font-medium">
            其他 {others.length} 个岗位（未进入精排）
          </summary>
          <p className="mt-2 text-xs text-muted-foreground">
            左侧是粗筛的相关度（0–3）。觉得 AI 漏掉了合适的岗位，可以调大精排岗位数后重新粗筛。
          </p>
          <ul className="mt-1 divide-y">
            {others.map((j) => (
              <OtherJobRow key={j.id} job={j} />
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

function CollectStep({ batch }: { batch: BatchDetail }) {
  const [text, setText] = useState("");
  const [open, setOpen] = useState(batch.total_jobs === 0);
  const extract = useExtractJobs(batch.id);

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-4">
        <div>
          <CardTitle>① 读取岗位</CardTitle>
          <CardDescription className="mt-1">
            {batch.total_jobs > 0
              ? `已读取 ${batch.total_jobs} 个岗位。列表有多页时，翻页后再粘贴一次，重复的岗位会自动去掉。`
              : "打开这家公司的招聘列表页，全选（Ctrl + A）复制，粘贴到下面。导航栏、页脚等内容不用删，AI 会识别出岗位。"}
          </CardDescription>
        </div>
        {!open && (
          <Button variant="outline" size="sm" onClick={() => setOpen(true)}>
            追加岗位
          </Button>
        )}
      </CardHeader>
      {open && (
        <CardContent className="flex flex-col gap-3">
          <Textarea
            aria-label="招聘列表页内容"
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="粘贴招聘列表页的全部内容"
            className="min-h-40 text-sm"
          />
          <div className="flex justify-end">
            <Button
              disabled={text.trim().length < 10 || extract.isPending}
              onClick={() =>
                extract.mutate(text, {
                  onSuccess: (r) => {
                    toast.success(
                      `读取到 ${r.added} 个新岗位${r.duplicated ? `，${r.duplicated} 个重复已跳过` : ""}`,
                    );
                    setText("");
                    setOpen(false);
                  },
                  onError: (err) => toast.error(err.message),
                })
              }
            >
              {extract.isPending && <Loader2 className="size-4 animate-spin" />}
              {extract.isPending ? "AI 识别中…" : "读取岗位"}
            </Button>
          </div>
        </CardContent>
      )}
    </Card>
  );
}

function ScreenStep({ batch, screened }: { batch: BatchDetail; screened: boolean }) {
  const screen = useScreen(batch.id);
  const filtered = batch.jobs.filter((j) => j.filtered_reason).length;
  // 有新岗位还没粗筛（读取后状态会回到 collecting）
  const stale = screened && batch.status === "collecting";

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-4">
        <div>
          <CardTitle>② 粗筛</CardTitle>
          <CardDescription className="mt-1">
            {screened && !stale
              ? `硬条件排除了 ${filtered} 个，AI 按岗位名判断相关度后，选出 ${batch.shortlisted_jobs} 个进入精排。`
              : stale
                ? "有新读取的岗位还没粗筛，重新粗筛一次。"
                : `先按城市、招聘类型、排除关键词过滤，再由 AI 根据岗位名和你的简历判断相关度，选出前 ${batch.top_n} 个。`}
          </CardDescription>
        </div>
        <Button
          variant={screened && !stale ? "outline" : "default"}
          size="sm"
          disabled={screen.isPending}
          onClick={() => screen.mutate(undefined, { onError: (err) => toast.error(err.message) })}
        >
          {screen.isPending ? (
            <Loader2 className="size-4 animate-spin" />
          ) : (
            <Filter className="size-4" />
          )}
          {screen.isPending ? "粗筛中…" : screened ? "重新粗筛" : "开始粗筛"}
        </Button>
      </CardHeader>
    </Card>
  );
}

function RankStep({
  batchId,
  pending,
  hasResults,
}: {
  batchId: string;
  pending: number;
  hasResults: boolean;
}) {
  const { state, start } = useRank(batchId);
  const running = state.status === "running";

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-4">
        <div className="flex-1">
          <CardTitle>③ 精排</CardTitle>
          <CardDescription className="mt-1">
            {running
              ? `正在逐个对照简历…已完成 ${state.done}/${state.total || "?"}`
              : pending > 0
                ? `${pending} 个岗位已有 JD、等待精排。AI 逐条对照岗位要求和你的简历，按和“岗位匹配”相同的规则计算匹配度。`
                : "全部完成。补充了新的 JD 后可以再精排一次。"}
          </CardDescription>
          {running && state.total > 0 && (
            <Progress value={(state.done / state.total) * 100} className="mt-3" />
          )}
          {state.status === "error" && (
            <p className="mt-2 text-sm text-destructive">{state.message}</p>
          )}
        </div>
        <Button
          size="sm"
          variant={pending > 0 ? "default" : "outline"}
          disabled={running}
          onClick={start}
        >
          {running ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
          {running ? "精排中…" : hasResults ? "重新精排" : "开始精排"}
        </Button>
      </CardHeader>
    </Card>
  );
}
