# 前端镜像：用 Next.js 的 standalone 输出，运行时只需要 node server.js，不需要完整的 node_modules
FROM node:26-alpine AS deps
# 不用 corepack：它的旧版本和 pnpm 12 不兼容，直接用 npm 装固定版本
RUN npm install -g pnpm@12.16.1
WORKDIR /app
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

FROM deps AS build
COPY . .
# 后端地址在构建时写进路由配置（next.config.ts 的 rewrites），所以是构建参数而不是运行时变量
ARG BACKEND_URL=http://backend:8000
ENV BACKEND_URL=$BACKEND_URL \
    NEXT_TELEMETRY_DISABLED=1
RUN pnpm build

FROM node:26-alpine
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
COPY --from=build /app/public ./public
EXPOSE 3000
CMD ["node", "server.js"]
