# OTT Stream Monitor — Web (static frontend + nginx reverse proxy) image
# Build context is the repository root (see deploy/docker-compose.yml).
#
# NOTE: pnpm-workspace.yaml pins platform binaries (esbuild/rollup/lightningcss/
# oxide) to linux-x64 only, so this build must run on amd64/x86_64.

# ---- Build stage: compile the React/Vite app from the pnpm workspace ----
FROM node:22-bookworm-slim AS build

RUN corepack enable && corepack prepare pnpm@10.26.1 --activate

WORKDIR /repo
COPY . .

RUN pnpm install --frozen-lockfile

# vite.config.ts requires PORT and BASE_PATH at build time. For a standalone
# deployment the app is served at the domain root, so BASE_PATH=/. PORT is only
# validated (dev-server port), not used by the production build.
RUN PORT=8080 BASE_PATH=/ pnpm --filter @workspace/ott-monitor run build

# ---- Serve stage: nginx serves the static build and proxies /api ----
FROM nginx:1.27-alpine AS serve

COPY deploy/web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /repo/artifacts/ott-monitor/dist/public /usr/share/nginx/html

EXPOSE 80
