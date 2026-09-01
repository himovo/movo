FROM node:20-slim AS build

WORKDIR /app

ARG VITE_BASE_PATH=/admin/
ARG VITE_ADMIN_API_BASE_URL=/admin-api
ENV VITE_BASE_PATH=${VITE_BASE_PATH} \
    VITE_ADMIN_API_BASE_URL=${VITE_ADMIN_API_BASE_URL}

COPY package*.json ./
RUN npm ci --legacy-peer-deps

COPY . .
RUN npm run build

FROM nginx:1.29.8-alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
