# Multi-stage: build the Vite SPA, then serve the static output through
# nginx with /api proxied to the api service. Same-origin (rather than
# cross-origin CORS) is deliberate: api/settings.py's session cookie is
# SameSite-capable and the design assumes the dashboard and API share an
# origin in a deployed environment, matching how vite's own dev-server proxy
# (web/vite.config.ts) behaves locally.
FROM node:20-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Types are generated from the committed fixture OpenAPI schema, not a live
# call to the api service: a plain `docker compose build` builds each image
# independently, with no guaranteed network path to another service's
# container, so a build-time call to `api:8000` would be unreliable ordering
# to depend on. `npm run generate:types` (against a real running API) is a
# local dev-time step, done before committing web/fixtures/openapi.json, not
# part of this image build - keeping the build itself deterministic and
# network-independent.
RUN npm run generate:types:fixture
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
