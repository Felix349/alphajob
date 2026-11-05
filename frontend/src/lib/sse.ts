/**
 * 读取 SSE（Server-Sent Events）响应流。
 *
 * 浏览器自带的 EventSource 只支持 GET 请求，而生成分析需要用 POST 传参数，
 * 所以这里直接读 fetch 返回的字节流，自己按 SSE 格式切分事件：
 *
 *   event: delta\r\n
 *   data: {"text": "..."}\r\n
 *   \r\n                     ← 空行表示一个事件结束
 */
export type SseEvent = { event: string; data: string };

export async function* readSse(response: Response, signal?: AbortSignal): AsyncGenerator<SseEvent> {
  if (!response.body) return;
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      if (signal?.aborted) return;
      const { value, done } = await reader.read();
      if (done) break;
      // stream: true —— 一个中文字符可能被拆在两个数据块里，解码器会等下一块再拼起来
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");

      let boundary: number;
      while ((boundary = buffer.indexOf("\n\n")) >= 0) {
        const block = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        let event = "message";
        const data: string[] = [];
        for (const line of block.split("\n")) {
          if (line.startsWith(":")) continue; // 注释行，sse-starlette 用它发心跳
          if (line.startsWith("event:")) event = line.slice(6).trim();
          else if (line.startsWith("data:")) data.push(line.slice(5).replace(/^ /, ""));
        }
        if (data.length > 0) yield { event, data: data.join("\n") };
      }
    }
  } finally {
    reader.releaseLock();
  }
}
