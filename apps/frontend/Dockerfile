# Frontend container (Azure Container Apps). Next.js 15 standalone server on :3000.
FROM node:20-slim AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci
COPY . .
# Public env is baked into the browser bundle at build time (NEXT_PUBLIC_*). azd
# passes them as --build-arg; Docker build args are NOT visible to `npm run build`
# unless declared as ARG and promoted to ENV first. Without this, the values are
# empty in the bundle → authConfigured=false → the app renders WITHOUT sign-in.
ARG NEXT_PUBLIC_ENTRA_TENANT_ID=""
ARG NEXT_PUBLIC_ENTRA_SPA_CLIENT_ID=""
ARG NEXT_PUBLIC_ENTRA_API_CLIENT_ID=""
ENV NEXT_PUBLIC_ENTRA_TENANT_ID=$NEXT_PUBLIC_ENTRA_TENANT_ID
ENV NEXT_PUBLIC_ENTRA_SPA_CLIENT_ID=$NEXT_PUBLIC_ENTRA_SPA_CLIENT_ID
ENV NEXT_PUBLIC_ENTRA_API_CLIENT_ID=$NEXT_PUBLIC_ENTRA_API_CLIENT_ID
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
