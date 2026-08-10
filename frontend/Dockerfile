# Frontend image for the timetable admin. Builds the Next.js standalone
# output (next.config.mjs sets output: "standalone"), then serves it with
# `next start`-equivalent `node server.js`. NEXT_PUBLIC_API_URL is a build
# arg so the browser-reachable backend URL is baked into the client bundle;
# per DD-019 the browser calls the backend directly (no proxy rewrite).
FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts

FROM node:20-alpine AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
COPY --from=build /app/public ./public

EXPOSE 3000
CMD ["node", "server.js"]
