FROM node:24.18.0-alpine AS dev
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
CMD ["sh", "-c", "npm ci && exec npm run dev"]

FROM dev AS build
RUN npm run build

FROM nginx:1.28-alpine AS prod
ENV PORT=8080 NGINX_ENVSUBST_FILTER=^PORT$
COPY deploy/nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist/ /usr/share/nginx/html/
