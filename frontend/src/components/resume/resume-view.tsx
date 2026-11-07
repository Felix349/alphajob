"use client";

import { FileUp, Save, Trash2 } from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { useDeleteResume, useResume, useSaveResume, useUploadResume } from "@/hooks/use-resume";
import { RESUME_LANGUAGES, type Resume, type ResumeLanguage } from "@/lib/api/resume";

const MIN_CHARS = 20;

const PLACEHOLDER: Record<ResumeLanguage, string> = {
  zh: "# 你的名字\n\n## 教育经历\n…\n\n## 项目经历\n…\n\n## 技能\n…",
  en: "# Your Name\n\n## Education\n…\n\n## Projects\n…\n\n## Skills\n…",
};

export function ResumeView() {
  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">我的简历</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          中文、英文简历各一份，上传 PDF 或直接粘贴文本。匹配分析会按 JD
          的语言自动选用对应的简历，提取后请检查一遍有没有遗漏或错字。
        </p>
      </div>
      <Tabs defaultValue="zh">
        <TabsList>
          {RESUME_LANGUAGES.map((l) => (
            <TabsTrigger key={l.value} value={l.value}>
              {l.label}
              <SlotStatus language={l.value} />
            </TabsTrigger>
          ))}
        </TabsList>
        {RESUME_LANGUAGES.map((l) => (
          // keepMounted：切换标签时保留另一份还没保存的修改
          <TabsContent key={l.value} value={l.value} keepMounted className="mt-4">
            <Slot language={l.value} />
          </TabsContent>
        ))}
      </Tabs>
    </div>
  );
}

/** 标签上的小圆点：这一栏是否已经有简历 */
function SlotStatus({ language }: { language: ResumeLanguage }) {
  const { data } = useResume(language);
  return (
    <span
      aria-label={data ? "已上传" : "未上传"}
      className={`ml-1.5 inline-block size-1.5 rounded-full ${data ? "bg-emerald-500" : "bg-muted-foreground/30"}`}
    />
  );
}

function Slot({ language }: { language: ResumeLanguage }) {
  const { data, isPending, error } = useResume(language);
  if (isPending) return <Skeleton className="h-96 w-full rounded-xl" />;
  if (error) return <p className="text-sm text-destructive">加载失败：{error.message}</p>;
  // key：上传新文件后内容变了，让编辑器用新内容重新初始化
  return <Editor key={data?.updated_at ?? "empty"} language={language} resume={data ?? null} />;
}

function Editor({ language, resume }: { language: ResumeLanguage; resume: Resume | null }) {
  const [text, setText] = useState(resume?.content_md ?? "");
  const fileInput = useRef<HTMLInputElement>(null);
  const save = useSaveResume(language);
  const upload = useUploadResume(language);
  const remove = useDeleteResume(language);
  const label = RESUME_LANGUAGES.find((l) => l.value === language)!.label;

  const dirty = text !== (resume?.content_md ?? "");
  const tooShort = text.trim().length < MIN_CHARS;

  function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = ""; // 允许再次选择同一个文件
    if (!file) return;
    if (dirty && !window.confirm("上传新文件会覆盖当前未保存的修改，继续吗？")) return;
    upload.mutate(file, {
      onSuccess: () => toast.success(`已从「${file.name}」提取简历，请检查内容`),
      onError: (err) => toast.error(err.message),
    });
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-4">
        <div>
          <CardTitle>{label}</CardTitle>
          <CardDescription className="mt-1">
            {resume
              ? `${resume.source === "pdf" ? `来自 ${resume.filename ?? "PDF"}` : "手动编辑"} · 更新于 ${new Date(resume.updated_at).toLocaleString("zh-CN")}`
              : `还没有${label}。支持 PDF、Markdown（.md）和纯文本（.txt），不超过 5 MB。`}
          </CardDescription>
        </div>
        <div className="flex shrink-0 gap-2">
          <input
            ref={fileInput}
            type="file"
            accept=".pdf,.md,.markdown,.txt"
            className="hidden"
            onChange={onFile}
          />
          <Button
            variant="outline"
            onClick={() => fileInput.current?.click()}
            disabled={upload.isPending}
          >
            <FileUp className="size-4" />
            {upload.isPending ? "解析中…" : "上传文件"}
          </Button>
          {resume && (
            <Button
              variant="ghost"
              size="icon"
              aria-label={`删除${label}`}
              disabled={remove.isPending}
              onClick={() => {
                if (!window.confirm(`确定删除${label}吗？已有的匹配分析不会受影响。`)) return;
                remove.mutate(undefined, {
                  onSuccess: () => toast.success(`${label}已删除`),
                  onError: (err) => toast.error(err.message),
                });
              }}
            >
              <Trash2 className="size-4" />
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <Textarea
          aria-label={`${label}内容`}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={PLACEHOLDER[language]}
          className="min-h-[480px] font-mono text-sm leading-relaxed"
        />
        <div className="flex items-center justify-between">
          <span className="text-xs text-muted-foreground">
            {text.length} 字{tooShort && text.length > 0 && ` · 至少需要 ${MIN_CHARS} 字`}
          </span>
          <Button
            disabled={!dirty || tooShort || save.isPending}
            onClick={() =>
              save.mutate(text.trim(), {
                onSuccess: () => toast.success(`${label}已保存`),
                onError: (err) => toast.error(err.message),
              })
            }
          >
            <Save className="size-4" />
            {save.isPending ? "保存中…" : "保存"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
