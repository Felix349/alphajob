"use client";

import { Mic, Square } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { formatDuration } from "@/lib/interview-meta";

export type Recording = { blob: Blob; seconds: number; name: string };

/**
 * 浏览器录音：用 MediaRecorder 把麦克风录成 webm/opus（Chrome、Edge）或 mp4（Safari）。
 * 后端会用 ffmpeg 统一转成语音识别需要的格式，所以这里不用关心编码细节。
 */
export function AudioRecorder({ onRecorded }: { onRecorded: (r: Recording | null) => void }) {
  const [state, setState] = useState<"idle" | "recording" | "done">("idle");
  const [seconds, setSeconds] = useState(0);
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);
  const startedAt = useRef(0);

  // 组件卸载时释放麦克风和预览地址
  useEffect(
    () => () => {
      recorder.current?.stream.getTracks().forEach((t) => t.stop());
      if (url) URL.revokeObjectURL(url);
    },
    [url],
  );

  useEffect(() => {
    if (state !== "recording") return;
    const timer = setInterval(() => setSeconds((Date.now() - startedAt.current) / 1000), 250);
    return () => clearInterval(timer);
  }, [state]);

  async function start() {
    setError(null);
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setError("当前浏览器不支持录音，请改用“上传文件”");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream);
      chunks.current = [];
      mr.ondataavailable = (e) => e.data.size > 0 && chunks.current.push(e.data);
      mr.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        const type = mr.mimeType || "audio/webm";
        const blob = new Blob(chunks.current, { type });
        const ext = type.includes("mp4") ? "m4a" : type.includes("ogg") ? "ogg" : "webm";
        const secs = (Date.now() - startedAt.current) / 1000;
        setUrl(URL.createObjectURL(blob));
        setState("done");
        onRecorded({ blob, seconds: secs, name: `口述回忆.${ext}` });
      };
      recorder.current = mr;
      startedAt.current = Date.now();
      setSeconds(0);
      mr.start(1000); // 每秒产出一块数据：录音中途出问题也不会全部丢失
      setState("recording");
    } catch {
      setError("没有拿到麦克风权限。请在浏览器地址栏左侧允许使用麦克风，或改用“上传文件”");
    }
  }

  function stop() {
    recorder.current?.stop();
  }

  function reset() {
    if (url) URL.revokeObjectURL(url);
    setUrl(null);
    setSeconds(0);
    setState("idle");
    onRecorded(null);
  }

  return (
    <div className="flex flex-col gap-3 rounded-lg border p-4">
      {state === "idle" && (
        <Button type="button" onClick={start} className="self-start">
          <Mic className="size-4" />
          开始录音
        </Button>
      )}
      {state === "recording" && (
        <div className="flex items-center gap-3">
          <span className="relative flex size-3">
            <span className="absolute inline-flex size-full animate-ping rounded-full bg-rose-400 opacity-75" />
            <span className="relative inline-flex size-3 rounded-full bg-rose-500" />
          </span>
          <span className="font-mono tabular-nums">{formatDuration(seconds)}</span>
          <Button type="button" variant="outline" size="sm" onClick={stop}>
            <Square className="size-3.5" />
            结束
          </Button>
        </div>
      )}
      {state === "done" && url && (
        <div className="flex flex-col gap-2">
          <audio controls src={url} className="w-full" />
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>时长 {formatDuration(seconds)}</span>
            <button type="button" onClick={reset} className="underline-offset-4 hover:underline">
              重新录制
            </button>
          </div>
        </div>
      )}
      <p className="text-xs text-muted-foreground">
        {state === "recording"
          ? "按面试顺序说：面试官问了什么、你是怎么回答的。想到哪说到哪，不用组织语言。"
          : "建议面试一结束就录，记忆最清楚。最长 30 分钟。"}
      </p>
      {error && <p className="text-sm text-destructive">{error}</p>}
    </div>
  );
}
