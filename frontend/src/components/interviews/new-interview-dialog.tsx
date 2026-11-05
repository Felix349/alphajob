"use client";

import { FileAudio, Keyboard, Mic } from "lucide-react";
import { useRef, useState } from "react";
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
import { Textarea } from "@/components/ui/textarea";
import { useCreateInterview } from "@/hooks/use-interviews";
import { cn } from "@/lib/utils";

import { AudioRecorder, type Recording } from "./audio-recorder";

type Mode = "record" | "upload" | "text";

const MODES: { value: Mode; label: string; icon: typeof Mic }[] = [
  { value: "record", label: "录音", icon: Mic },
  { value: "upload", label: "上传录音", icon: FileAudio },
  { value: "text", label: "文字", icon: Keyboard },
];

const MIN_TEXT = 30;

export function NewInterviewDialog({
  appId,
  defaultRound,
  open,
  onOpenChange,
  onCreated,
}: {
  appId: string;
  defaultRound: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated?: (id: string) => void;
}) {
  const [mode, setMode] = useState<Mode>("record");
  const [round, setRound] = useState(defaultRound);
  const [heldOn, setHeldOn] = useState(() => new Date().toLocaleDateString("sv-SE")); // YYYY-MM-DD
  const [text, setText] = useState("");
  const [recording, setRecording] = useState<Recording | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const create = useCreateInterview(appId);

  const ready =
    round.trim().length > 0 &&
    (mode === "text" ? text.trim().length >= MIN_TEXT : mode === "record" ? !!recording : !!file);

  function submit() {
    create.mutate(
      {
        round: round.trim(),
        heldOn,
        ...(mode === "text"
          ? { text: text.trim() }
          : mode === "record"
            ? { audio: recording!.blob, audioName: recording!.name }
            : { audio: file!, audioName: file!.name }),
      },
      {
        onSuccess: (interview) => {
          toast.success("已提交，正在后台整理复盘，大约需要 1 分钟");
          onOpenChange(false);
          onCreated?.(interview.id);
        },
        onError: (err) => toast.error(err.message),
      },
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>新建面试复盘</DialogTitle>
          <DialogDescription>
            把面试过程回忆出来，AI 会整理出每道题、评估你的回答，并给出改进版本和下一轮建议。
          </DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-2 gap-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="iv-round">轮次</Label>
            <Input id="iv-round" value={round} onChange={(e) => setRound(e.target.value)} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="iv-date">面试日期</Label>
            <Input
              id="iv-date"
              type="date"
              value={heldOn}
              onChange={(e) => setHeldOn(e.target.value)}
            />
          </div>
        </div>

        <div role="radiogroup" aria-label="回忆方式" className="flex gap-1 rounded-lg bg-muted p-1">
          {MODES.map(({ value, label, icon: Icon }) => (
            <button
              key={value}
              type="button"
              role="radio"
              aria-checked={mode === value}
              onClick={() => setMode(value)}
              className={cn(
                "flex flex-1 items-center justify-center gap-1.5 rounded-md py-1.5 text-sm transition-colors",
                mode === value
                  ? "bg-background shadow-xs"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              <Icon className="size-4" />
              {label}
            </button>
          ))}
        </div>

        {mode === "record" && <AudioRecorder onRecorded={setRecording} />}

        {mode === "upload" && (
          <div className="flex flex-col gap-2 rounded-lg border border-dashed p-4">
            <input
              ref={fileInput}
              type="file"
              accept="audio/*,.m4a,.webm,.amr"
              className="hidden"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
            <Button
              type="button"
              variant="outline"
              className="self-start"
              onClick={() => fileInput.current?.click()}
            >
              <FileAudio className="size-4" />
              选择录音文件
            </Button>
            <p className="text-xs text-muted-foreground">
              {file
                ? `${file.name}（${(file.size / 1024 / 1024).toFixed(1)} MB）`
                : "支持手机录音（m4a）、mp3、wav、webm 等常见格式，不超过 100 MB、30 分钟。"}
            </p>
          </div>
        )}

        {mode === "text" && (
          <div className="flex flex-col gap-1.5">
            <Textarea
              aria-label="面试回忆"
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder={
                "按顺序写下面试官问了什么、你是怎么答的，例如：\n1. 自我介绍\n2. 问项目里的长期记忆怎么设计，我说用向量库……\n3. 手写 LRU，我用哈希表 + 双向链表……"
              }
              className="min-h-48"
            />
            <span className="text-xs text-muted-foreground">
              {text.trim().length} 字{text.trim().length < MIN_TEXT && `，至少 ${MIN_TEXT} 字`}
            </span>
          </div>
        )}

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button onClick={submit} disabled={!ready || create.isPending}>
            {create.isPending ? "上传中…" : "提交复盘"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
