# Build context = repo root. Builds the SPA, then serves it with Caddy (auto HTTPS) and proxies /api to the backend.
FROM node:22-alpine AS build
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM caddy:2-alpine
COPY --from=build /web/dist /srv
COPY infra/prod/Caddyfile /etc/caddy/Caddyfile
