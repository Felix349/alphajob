/** 统一的请求封装：自动处理 JSON、Cookie 和错误信息。 */

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

type FastApiValidationError = { loc: (string | number)[]; msg: string };

// 后端 422 校验错误默认是英文，常见字段转成中文提示
const FIELD_MESSAGES: Record<string, string> = {
  email: "邮箱地址无效，请检查后重试",
  password: "密码不符合要求（8–128 位）",
};

function validationMessage(d: FastApiValidationError): string {
  const field = d.loc[d.loc.length - 1];
  return (typeof field === "string" && FIELD_MESSAGES[field]) || d.msg;
}

function extractMessage(body: unknown, status: number): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    // 422 校验错误：detail 是一个数组
    if (Array.isArray(detail) && detail.length > 0) {
      return [...new Set((detail as FastApiValidationError[]).map(validationMessage))].join("；");
    }
  }
  return `请求失败（${status}）`;
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`/api${path}`, {
    ...init,
    credentials: "same-origin",
    headers: {
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...init.headers,
    },
  });

  if (res.status === 204) return undefined as T;

  const body: unknown = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, extractMessage(body, res.status));
  return body as T;
}
