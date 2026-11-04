import { apiFetch } from "./client";
import type { components } from "./schema";

// 类型直接来自后端 OpenAPI 自动生成的 schema.d.ts，后端改了字段，这里会编译报错
export type User = components["schemas"]["UserOut"];
export type LoginInput = components["schemas"]["LoginRequest"];
export type RegisterInput = components["schemas"]["RegisterRequest"];

export const authApi = {
  me: () => apiFetch<User>("/auth/me"),
  login: (data: LoginInput) =>
    apiFetch<User>("/auth/login", { method: "POST", body: JSON.stringify(data) }),
  register: (data: RegisterInput) =>
    apiFetch<User>("/auth/register", { method: "POST", body: JSON.stringify(data) }),
  logout: () => apiFetch<void>("/auth/logout", { method: "POST" }),
};
