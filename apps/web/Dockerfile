# syntax=docker/dockerfile:1.7

FROM node:20-bookworm-slim AS base

ENV PNPM_HOME=/pnpm
ENV PATH=$PNPM_HOME:$PATH

WORKDIR /workspace

RUN corepack enable && pnpm config set store-dir /pnpm/store

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml turbo.json ./
COPY apps/web/package.json apps/web/package.json
COPY packages/shared-types/package.json packages/shared-types/package.json

RUN pnpm install --frozen-lockfile

FROM base AS dev

COPY . .

EXPOSE 3000

CMD ["pnpm", "--filter", "web", "dev", "--hostname", "0.0.0.0", "--port", "3000"]

FROM base AS build

COPY . .

RUN pnpm --filter @sustainability/shared-types build
RUN pnpm --filter web build

FROM base AS production

ENV NODE_ENV=production

COPY . .
COPY --from=build /workspace/apps/web/.next /workspace/apps/web/.next

EXPOSE 3000

CMD ["pnpm", "--filter", "web", "start", "--hostname", "0.0.0.0", "--port", "3000"]
