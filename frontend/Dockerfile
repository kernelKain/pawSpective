FROM node:22-alpine AS dependencies

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci


FROM node:22-alpine AS builder

WORKDIR /app

ARG NEXT_PUBLIC_API_BASE_URL
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL

COPY --from=dependencies /app/node_modules ./node_modules
COPY . .

RUN npm run build


FROM node:22-alpine AS runner

ENV NODE_ENV=production
ENV PORT=3000
ENV HOSTNAME=0.0.0.0

RUN addgroup --system --gid 10001 nextjs \
    && adduser --system --uid 10001 nextjs

WORKDIR /app

COPY --from=builder \
    --chown=nextjs:nextjs \
    /app/public \
    ./public

COPY --from=builder \
    --chown=nextjs:nextjs \
    /app/.next/standalone \
    ./

COPY --from=builder \
    --chown=nextjs:nextjs \
    /app/.next/static \
    ./.next/static

USER nextjs

EXPOSE 3000

CMD ["node", "server.js"]