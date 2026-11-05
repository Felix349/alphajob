"use client";

import Link from "next/link";
import { useDeferredValue, useMemo, useState } from "react";

import { QuestionCard } from "@/components/interviews/interview-detail-view";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { useQuestions } from "@/hooks/use-interviews";
import type { Mastery, QuestionFilters } from "@/lib/api/interviews";
import { MASTERY } from "@/lib/interview-meta";

export function QuestionBank() {
  const [company, setCompany] = useState("");
  const [tag, setTag] = useState("");
  const [mastery, setMastery] = useState<Mastery | "">("");
  const [search, setSearch] = useState("");
  // 输入搜索词时不必每敲一个字就请求一次：useDeferredValue 让请求跟在输入后面，打字不卡顿
  const q = useDeferredValue(search.trim());

  const filters: QuestionFilters = {
    company: company || undefined,
    tag: tag || undefined,
    mastery: mastery || undefined,
    q: q || undefined,
  };
  const { data: questions, isPending, error } = useQuestions(filters);
  // 筛选项来自“全部题目”，这样选了一个公司之后，其他公司的选项不会消失
  const { data: all = [] } = useQuestions({});
  const companies = useMemo(() => [...new Set(all.map((x) => x.company))].sort(), [all]);
  const tags = useMemo(() => {
    const count = new Map<string, number>();
    all.forEach((x) => x.tags.forEach((t) => count.set(t, (count.get(t) ?? 0) + 1)));
    return [...count.entries()].sort((a, b) => b[1] - a[1]);
  }, [all]);

  const mastered = all.filter((x) => x.mastery === "mastered").length;

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">题库</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          你在真实面试中被问过的所有题目。
          {all.length > 0 && `共 ${all.length} 道，已掌握 ${mastered} 道。`}
          没掌握、得分低的排在最前面。
        </p>
      </div>

      <div className="grid gap-2 sm:grid-cols-4">
        <Input
          aria-label="搜索题目"
          placeholder="搜索题目或参考回答"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <NativeSelect
          aria-label="公司"
          value={company}
          onChange={(e) => setCompany(e.target.value)}
        >
          <option value="">全部公司</option>
          {companies.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </NativeSelect>
        <NativeSelect aria-label="知识点" value={tag} onChange={(e) => setTag(e.target.value)}>
          <option value="">全部知识点</option>
          {tags.map(([t, n]) => (
            <option key={t} value={t}>
              {t}（{n}）
            </option>
          ))}
        </NativeSelect>
        <NativeSelect
          aria-label="掌握程度"
          value={mastery}
          onChange={(e) => setMastery(e.target.value as Mastery | "")}
        >
          <option value="">全部状态</option>
          {Object.entries(MASTERY).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </NativeSelect>
      </div>

      {isPending && <Skeleton className="h-64 w-full rounded-xl" />}
      {error && <p className="text-sm text-destructive">加载失败：{error.message}</p>}
      {questions && all.length === 0 && (
        <div className="rounded-xl border border-dashed p-12 text-center text-sm">
          <p className="font-medium">题库还是空的</p>
          <p className="mt-1 text-muted-foreground">
            完成一次面试复盘后，被问到的题目会自动出现在这里。
          </p>
        </div>
      )}
      {questions && all.length > 0 && questions.length === 0 && (
        <p className="text-center text-sm text-muted-foreground">没有符合条件的题目</p>
      )}
      <div className="flex flex-col gap-3">
        {questions?.map((question) => (
          <QuestionCard
            key={question.id}
            question={question}
            meta={
              <Link
                href={`/interviews/${question.interview_id}`}
                className="text-xs text-muted-foreground hover:underline"
              >
                {question.company} · {question.role} · {question.round}
              </Link>
            }
          />
        ))}
      </div>
    </div>
  );
}
