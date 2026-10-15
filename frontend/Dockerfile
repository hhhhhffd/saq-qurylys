# syntax=docker/dockerfile:1

# ---- build: pnpm + Vite -----------------------------------------------------
FROM node:22-alpine AS build
WORKDIR /app
RUN npm install -g pnpm@10.15.1
COPY package.json pnpm-lock.yaml ./
RUN --mount=type=cache,id=pnpm-store,target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile
COPY . .
# Optional MapLibre style (defaults to OpenFreeMap "positron" when empty).
ARG VITE_MAP_STYLE_URL=""
ENV VITE_MAP_STYLE_URL=${VITE_MAP_STYLE_URL}
RUN pnpm build

# ---- serve: nginx (SPA + /api proxy) ---------------------------------------
FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
