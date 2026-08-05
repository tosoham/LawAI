# syntax=docker/dockerfile:1

# LawAI frontend image (Next.js 14, Pages Router).
#
# Note on NEXT_PUBLIC_*: those values are inlined into the client bundle at
# BUILD time, not read at runtime. NEXT_PUBLIC_API_URL is therefore a build
# argument -- and it must be an address the *browser* can reach, so it points at
# the published host port, not the compose service name.

# --------------------------------------------------------------- deps --------
FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

# -------------------------------------------------------------- builder ------
FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ARG NEXT_PUBLIC_API_VERSION=v1
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_PUBLIC_API_VERSION=$NEXT_PUBLIC_API_VERSION \
    NEXT_TELEMETRY_DISABLED=1

RUN npm run build

# -------------------------------------------------------------- runtime ------
FROM node:20-alpine AS runtime
WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

RUN addgroup -g 10001 -S nodejs && adduser -u 10001 -S nextjs -G nodejs

# The standalone output already contains the trimmed node_modules and server.js;
# static assets and public/ are the two things it does not copy for you.
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs
EXPOSE 3000

CMD ["node", "server.js"]
