import type { NextConfig } from "next";

// 后端地址：开发时是本机的 FastAPI；Docker 一键启动时由环境变量覆盖为容器地址
const BACKEND_URL = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  // 构建产物自带一个最小的 Node 服务（.next/standalone），Docker 镜像只需拷贝它
  output: "standalone",
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  // 浏览器只访问前端的 /api/*，由 Next.js 转发给后端。
  // 前后端对浏览器来说是同一个域名：Cookie 自动携带，也不需要配置跨域（CORS）。
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${BACKEND_URL}/api/:path*` }];
  },
};

export default nextConfig;
