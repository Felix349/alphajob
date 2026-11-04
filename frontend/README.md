# AlphaJob 前端

Next.js 16（App Router）+ TypeScript + Tailwind CSS 4 + shadcn/ui。运行方式和整体说明见仓库根目录的 [README](../README.md)。

## 目录

```
src/
├── app/
│   ├── (auth)/         登录、注册页（未登录可访问）
│   ├── (app)/          登录后的页面，共用侧边栏布局
│   ├── layout.tsx      根布局
│   └── providers.tsx   TanStack Query、Toast 等全局 Provider
├── components/
│   ├── ui/             shadcn/ui 组件（可以直接修改）
│   ├── auth/           登录注册表单
│   └── layout/         应用外壳、占位页
├── hooks/              自定义 Hook
├── lib/api/            请求封装与接口类型（schema.d.ts 由 pnpm gen:api 生成，不要手改）
└── proxy.ts            路由守卫（Next.js 16 中替代 middleware.ts）
```

## 约定

- 所有接口请求都走 `/api/*`，由 `next.config.ts` 的 rewrites 转发给后端。
- 接口的类型来自后端自动生成的 `src/lib/api/schema.d.ts`。后端改了接口后运行 `pnpm gen:api`，CI 会检查生成文件是否最新。
