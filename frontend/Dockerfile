FROM node:22-alpine AS build
WORKDIR /usr/src/app
COPY package.json ./
RUN npm install --no-audit --no-fund
COPY index.html tsconfig.json ./
COPY src ./src
RUN npm run build

# Upstream unprivileged nginx listens on 8080 and runs as UID 101.
FROM nginxinc/nginx-unprivileged:1.27-alpine
COPY --chown=101:101 nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build --chown=101:101 /usr/src/app/dist /usr/share/nginx/html
USER 101:101
EXPOSE 8080
