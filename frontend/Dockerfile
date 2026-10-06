FROM node:22-alpine AS build

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./

ARG VITE_API_BASE=
ENV VITE_API_BASE=${VITE_API_BASE}

RUN npm run build

FROM nginx:alpine

COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

LABEL org.opencontainers.image.source="https://github.com/Jonesxq/douyin_RAG"

EXPOSE 80
