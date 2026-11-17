"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { useCreateBatch } from "@/hooks/use-screening";
import { JOB_TYPES, type JobType } from "@/lib/api/screening";
import { cn } from "@/lib/utils";

/** “北京、上海 / 深圳” → ["北京", "上海", "深圳"]：中英文逗号、顿号、斜杠、空格都算分隔 */
const splitList = (s: string) =>
  s
    .split(/[,，、/\s]+/)
    .map((x) => x.trim())
    .filter(Boolean);

export function NewBatchDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const router = useRouter();
  const create = useCreateBatch();
  const [company, setCompany] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [cities, setCities] = useState("");
  const [jobTypes, setJobTypes] = useState<JobType[]>(["校招"]);
  const [exclude, setExclude] = useState("销售、客服、财务、人力");
  const [topN, setTopN] = useState(15);
  const [resumeLanguage, setResumeLanguage] = useState<"auto" | "zh" | "en">("auto");

  function toggleType(t: JobType) {
    setJobTypes((prev) => (prev.includes(t) ? prev.filter((x) => x !== t) : [...prev, t]));
  }

  function submit() {
    create.mutate(
      {
        company: company.trim(),
        source_url: sourceUrl.trim() || null,
        resume_language: resumeLanguage === "auto" ? null : resumeLanguage,
        top_n: topN,
        filters: {
          cities: splitList(cities),
          job_types: jobTypes,
          exclude_keywords: splitList(exclude),
        },
      },
      {
        onSuccess: (batch) => {
          onOpenChange(false);
          router.push(`/screening/${batch.id}`);
        },
        onError: (err) => toast.error(err.message),
      },
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>新建岗位筛选</DialogTitle>
          <DialogDescription>
            一家公司的招聘列表建一次。硬条件会先把明显不合适的岗位排除掉，再由 AI 粗筛、精排。
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="sb-company">公司</Label>
            <Input
              id="sb-company"
              value={company}
              onChange={(e) => setCompany(e.target.value)}
              placeholder="例如：华为"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="sb-url">招聘列表页链接（可选）</Label>
            <Input
              id="sb-url"
              value={sourceUrl}
              onChange={(e) => setSourceUrl(e.target.value)}
              placeholder="https://…  用来把页面里的相对链接补全"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="sb-cities">城市（可选）</Label>
            <Input
              id="sb-cities"
              value={cities}
              onChange={(e) => setCities(e.target.value)}
              placeholder="北京、上海；不填表示不限"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <span className="text-sm font-medium">招聘类型</span>
            <div className="flex gap-2">
              {JOB_TYPES.map((t) => (
                <button
                  key={t}
                  type="button"
                  aria-pressed={jobTypes.includes(t)}
                  onClick={() => toggleType(t)}
                  className={cn(
                    "rounded-md border px-3 py-1 text-sm transition-colors",
                    jobTypes.includes(t)
                      ? "border-primary bg-primary text-primary-foreground"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {t}
                </button>
              ))}
            </div>
            <span className="text-xs text-muted-foreground">
              页面上没写招聘类型的岗位不会被排除。都不选表示不限。
            </span>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="sb-exclude">排除关键词</Label>
            <Input id="sb-exclude" value={exclude} onChange={(e) => setExclude(e.target.value)} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="sb-topn">精排岗位数</Label>
              <Input
                id="sb-topn"
                type="number"
                min={1}
                max={30}
                value={topN}
                onChange={(e) => setTopN(Math.min(30, Math.max(1, Number(e.target.value) || 1)))}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="sb-lang">使用的简历</Label>
              <NativeSelect
                id="sb-lang"
                value={resumeLanguage}
                onChange={(e) => setResumeLanguage(e.target.value as typeof resumeLanguage)}
              >
                <option value="auto">自动（按岗位语言）</option>
                <option value="zh">中文简历</option>
                <option value="en">英文简历</option>
              </NativeSelect>
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button onClick={submit} disabled={!company.trim() || create.isPending}>
            {create.isPending ? "创建中…" : "下一步：读取岗位"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
