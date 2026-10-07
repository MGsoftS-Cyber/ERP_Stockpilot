FROM node:24-alpine AS base
WORKDIR /workspace
RUN corepack enable
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json ./apps/web/package.json
RUN pnpm install --frozen-lockfile --ignore-scripts
COPY apps/web ./apps/web
WORKDIR /workspace/apps/web

FROM base AS development
EXPOSE 5173
# Refresh persisted dependency volumes when a new week adds a frontend library.
CMD ["sh", "-c", "pnpm --dir /workspace install --frozen-lockfile --ignore-scripts && pnpm dev"]

FROM base AS build
RUN pnpm build
