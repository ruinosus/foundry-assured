# Frontend container (Azure Container Apps). Next.js 15 standalone server on :3000.
FROM node:20-slim AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci
COPY . .
# Public env baked at build time must be present here (NEXT_PUBLIC_*). azd passes
# them as build args / env when building the image.
RUN npm run build

FROM node:20-slim AS run
WORKDIR /app
ENV NODE_ENV=production
ENV PORT=3000
# Standalone output: server.js + minimal node_modules, plus static assets.
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
COPY --from=build /app/public ./public
EXPOSE 3000
CMD ["node", "server.js"]
