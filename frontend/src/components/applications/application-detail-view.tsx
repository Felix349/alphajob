"use client";

import { ArrowLeft, ExternalLink, Trash2 } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import {
  useApplication,
  useDeleteApplication,
  useUpdateApplication,
} from "@/hooks/use-applications";
import type { ApplicationDetail, Stage } from "@/lib/api/applications";
import { ApiError } from "@/lib/api/client";
import { formatDate } from "@/lib/format";
import { STAGES } from "@/lib/stages";

import { EventPanel } from "./event-panel";
import { JdPanel } from "./jd-panel";
import { MatchPanel } from "./match-panel";
import { PrepChecklist } from "./prep-checklist";

export function ApplicationDetailView() {
  const { id } = useParams<{ id: string }>();
  const { data, isPending, error } = useApplication(id);

  if (isPending) return <Skeleton className="h-96 w-full max-w-5xl rounded-xl" />;
  if (error) {
    const notFound = error instanceof ApiError && error.status === 404;
    return (
      <div className="mx-auto max-w-md py-16 text-center">
        <p className="font-medium">{notFound ? "投递记录不存在" : `加载失败：${error.message}`}</p>
        <Link href="/board" className="mt-4 inline-block text-sm underline">
          返回看板
        </Link>
      </div>
    );
  }
  // key：切换到另一条记录时重置表单状态
  return <Detail key={data.id} app={data} />;
}

function Detail({ app }: { app: ApplicationDetail }) {
  const update = useUpdateApplication();

  function changeStage(stage: Stage) {
    update.mutate(
      { id: app.id, data: { stage } },
      { onError: (err) => toast.error(`更新失败：${err.message}`) },
    );
  }

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6">
      <div>
        <Link
          href="/board"
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="size-4" />
          返回看板
        </Link>
        <div className="mt-3 flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">{app.company}</h1>
            <p className="mt-1 text-muted-foreground">
              {app.role}
              {app.applied_at && ` · ${formatDate(app.applied_at)} 投递`}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <NativeSelect
              aria-label="投递阶段"
              value={app.stage}
              onChange={(e) => changeStage(e.target.value as Stage)}
              className="w-32"
            >
              {STAGES.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </NativeSelect>
            {app.job_url && (
              <a
                href={app.job_url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex h-8 items-center gap-1 rounded-lg border px-2.5 text-sm hover:bg-muted"
              >
                <ExternalLink className="size-4" />
                岗位页
              </a>
            )}
            <DeleteButton app={app} />
          </div>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
        <div className="flex flex-col gap-6">
          <MatchPanel app={app} />
          <JdPanel app={app} />
          <InfoForm app={app} />
        </div>
        <div className="flex flex-col gap-6">
          <PrepChecklist appId={app.id} />
          <EventPanel appId={app.id} events={app.events} />
        </div>
      </div>
    </div>
  );
}

function InfoForm({ app }: { app: ApplicationDetail }) {
  const update = useUpdateApplication();
  const [values, setValues] = useState({
    company: app.company,
    role: app.role,
    location: app.location ?? "",
    channel: app.channel ?? "",
    job_url: app.job_url ?? "",
    notes: app.notes ?? "",
  });
  const set = (k: keyof typeof values) => (e: { target: { value: string } }) =>
    setValues((v) => ({ ...v, [k]: e.target.value }));

  const dirty =
    values.company !== app.company ||
    values.role !== app.role ||
    values.location !== (app.location ?? "") ||
    values.channel !== (app.channel ?? "") ||
    values.job_url !== (app.job_url ?? "") ||
    values.notes !== (app.notes ?? "");

  function save(e: React.FormEvent) {
    e.preventDefault();
    if (!values.company.trim() || !values.role.trim()) {
      toast.error("公司和岗位不能为空");
      return;
    }
    const orNull = (v: string) => v.trim() || null;
    update.mutate(
      {
        id: app.id,
        data: {
          company: values.company.trim(),
          role: values.role.trim(),
          location: orNull(values.location),
          channel: orNull(values.channel),
          job_url: orNull(values.job_url),
          notes: orNull(values.notes),
        },
      },
      {
        onSuccess: () => toast.success("已保存"),
        onError: (err) => toast.error(err.message),
      },
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>基本信息</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={save} className="grid gap-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field id="company" label="公司">
              <Input id="company" value={values.company} onChange={set("company")} />
            </Field>
            <Field id="role" label="岗位">
              <Input id="role" value={values.role} onChange={set("role")} />
            </Field>
            <Field id="location" label="地点">
              <Input id="location" value={values.location} onChange={set("location")} />
            </Field>
            <Field id="channel" label="投递渠道">
              <Input id="channel" value={values.channel} onChange={set("channel")} />
            </Field>
          </div>
          <Field id="job_url" label="岗位链接">
            <Input id="job_url" value={values.job_url} onChange={set("job_url")} />
          </Field>
          <Field id="notes" label="备注">
            <Textarea
              id="notes"
              value={values.notes}
              onChange={set("notes")}
              placeholder="内推人、联系方式、面试官风格……"
              className="min-h-24"
            />
          </Field>
          <div className="flex justify-end">
            <Button type="submit" disabled={!dirty || update.isPending}>
              {update.isPending ? "保存中…" : "保存修改"}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

function DeleteButton({ app }: { app: ApplicationDetail }) {
  const [open, setOpen] = useState(false);
  const remove = useDeleteApplication();
  const router = useRouter();

  function confirm() {
    remove.mutate(app.id, {
      onSuccess: () => {
        toast.success("已删除");
        router.replace("/board");
      },
      onError: (err) => toast.error(err.message),
    });
  }

  return (
    <>
      <Button variant="ghost" size="icon" aria-label="删除投递" onClick={() => setOpen(true)}>
        <Trash2 className="size-4" />
      </Button>
      <AlertDialog open={open} onOpenChange={setOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>删除这条投递？</AlertDialogTitle>
            <AlertDialogDescription>
              「{app.company} · {app.role}」及其 {app.events.length} 个日程会被永久删除，无法恢复。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <Button variant="destructive" onClick={confirm} disabled={remove.isPending}>
              删除
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}

function Field({ id, label, children }: { id: string; label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      {children}
    </div>
  );
}
