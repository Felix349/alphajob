"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Sparkles } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { Badge } from "@/components/ui/badge";
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
import { Textarea } from "@/components/ui/textarea";
import { useCreateApplication, useParseJd } from "@/hooks/use-applications";
import type { ParsedJD, Stage } from "@/lib/api/applications";
import { ApiError } from "@/lib/api/client";
import { STAGES } from "@/lib/stages";

const schema = z.object({
  company: z.string().trim().min(1, { error: "请填写公司" }).max(128),
  role: z.string().trim().min(1, { error: "请填写岗位" }).max(128),
  location: z.string().max(128),
  channel: z.string().max(64),
  job_url: z.string().max(1024),
  stage: z.string(),
});
type FormValues = z.infer<typeof schema>;

const EMPTY: FormValues = {
  company: "",
  role: "",
  location: "",
  channel: "",
  job_url: "",
  stage: "wishlist",
};

const orNull = (v: string) => (v.trim() ? v.trim() : null);

/**
 * 新建投递：第一步粘贴 JD 交给大模型解析，第二步确认、修改解析结果后保存。
 * 大模型只负责“填表”，最终保存什么由用户决定。
 */
export function NewApplicationDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [step, setStep] = useState<"paste" | "form">("paste");
  const [jdText, setJdText] = useState("");
  const [parsed, setParsed] = useState<ParsedJD | null>(null);
  const parse = useParseJd();
  const create = useCreateApplication();
  const form = useForm<FormValues>({ resolver: zodResolver(schema), defaultValues: EMPTY });

  function reset() {
    setStep("paste");
    setJdText("");
    setParsed(null);
    form.reset(EMPTY);
  }

  function handleOpenChange(next: boolean) {
    onOpenChange(next);
    if (!next) reset();
  }

  function goToForm(result: ParsedJD | null) {
    setParsed(result);
    form.reset({
      ...EMPTY,
      company: result?.company ?? "",
      role: result?.role ?? "",
      location: result?.location ?? "",
    });
    setStep("form");
  }

  function handleParse() {
    parse.mutate(jdText, {
      onSuccess: (result) => {
        toast.success("解析完成，请确认信息");
        goToForm(result);
      },
      onError: (err) => {
        // 没配置 API Key（503）或模型出错时，不阻塞用户：直接进入手动填写
        const hint = err instanceof ApiError && err.status === 503 ? "，请手动填写" : "";
        toast.error(`${err.message}${hint}`);
        goToForm(null);
      },
    });
  }

  function onSubmit(values: FormValues) {
    create.mutate(
      {
        company: values.company.trim(),
        role: values.role.trim(),
        location: orNull(values.location),
        channel: orNull(values.channel),
        job_url: orNull(values.job_url),
        stage: values.stage as Stage,
        jd_text: orNull(jdText),
        jd_parsed: parsed,
      },
      {
        onSuccess: (app) => {
          toast.success(`已添加：${app.company} · ${app.role}`);
          handleOpenChange(false);
        },
        onError: (err) => toast.error(err.message),
      },
    );
  }

  const { errors } = form.formState;

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-xl">
        {step === "paste" ? (
          <>
            <DialogHeader>
              <DialogTitle>新建投递</DialogTitle>
              <DialogDescription>
                粘贴岗位描述（JD），AI 会帮你提取公司、岗位、要求和技术栈。
              </DialogDescription>
            </DialogHeader>
            <Textarea
              value={jdText}
              onChange={(e) => setJdText(e.target.value)}
              placeholder="把招聘页上的岗位描述整段复制到这里……"
              className="h-64 resize-none"
              autoFocus
            />
            <DialogFooter>
              <Button variant="ghost" onClick={() => goToForm(null)}>
                跳过，手动填写
              </Button>
              <Button onClick={handleParse} disabled={jdText.trim().length < 20 || parse.isPending}>
                <Sparkles className="size-4" />
                {parse.isPending ? "解析中…" : "智能解析"}
              </Button>
            </DialogFooter>
          </>
        ) : (
          <form onSubmit={form.handleSubmit(onSubmit)} noValidate className="grid gap-4">
            <DialogHeader>
              <DialogTitle>{parsed ? "确认投递信息" : "填写投递信息"}</DialogTitle>
              <DialogDescription>
                {parsed ? "以下内容由 AI 从 JD 中提取，请检查后保存。" : "带 * 的为必填项。"}
              </DialogDescription>
            </DialogHeader>

            {parsed && <ParsedPreview parsed={parsed} />}

            <div className="grid grid-cols-2 gap-3">
              <Field id="new-company" label="公司 *" error={errors.company?.message}>
                <Input
                  id="new-company"
                  {...form.register("company")}
                  aria-invalid={!!errors.company}
                />
              </Field>
              <Field id="new-role" label="岗位 *" error={errors.role?.message}>
                <Input id="new-role" {...form.register("role")} aria-invalid={!!errors.role} />
              </Field>
              <Field id="new-location" label="地点">
                <Input id="new-location" {...form.register("location")} />
              </Field>
              <Field id="new-channel" label="投递渠道">
                <Input
                  id="new-channel"
                  {...form.register("channel")}
                  placeholder="官网 / 内推 / 牛客…"
                />
              </Field>
              <Field id="new-stage" label="当前阶段">
                <NativeSelect id="new-stage" {...form.register("stage")}>
                  {STAGES.map((s) => (
                    <option key={s.value} value={s.value}>
                      {s.label}
                    </option>
                  ))}
                </NativeSelect>
              </Field>
              <Field id="new-job_url" label="岗位链接">
                <Input id="new-job_url" {...form.register("job_url")} placeholder="https://" />
              </Field>
            </div>

            <DialogFooter>
              <Button type="button" variant="ghost" onClick={() => setStep("paste")}>
                上一步
              </Button>
              <Button type="submit" disabled={create.isPending}>
                {create.isPending ? "保存中…" : "保存"}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}

function ParsedPreview({ parsed }: { parsed: ParsedJD }) {
  return (
    <div className="rounded-lg border bg-muted/40 p-3 text-sm">
      <p className="font-medium">{parsed.summary}</p>
      {parsed.tech_stack.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {parsed.tech_stack.map((t) => (
            <Badge key={t} variant="secondary">
              {t}
            </Badge>
          ))}
        </div>
      )}
      <p className="mt-2 text-xs text-muted-foreground">
        已提取 {parsed.responsibilities.length} 条职责、{parsed.requirements.length} 条要求
        {parsed.deadline && `，截止日期 ${parsed.deadline}`}
      </p>
    </div>
  );
}

function Field({
  id,
  label,
  error,
  children,
}: {
  id: string;
  label: string;
  error?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      {children}
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  );
}
