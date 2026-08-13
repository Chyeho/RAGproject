# ============ 前端 Vue 应用 Dockerfile ============
# 阶段一：构建 Vue 项目

FROM node:22-alpine AS builder

WORKDIR /app

# 利用 Docker 层缓存 —— 先拷贝依赖文件
COPY package.json package-lock.json* yarn.lock* pnpm-lock.yaml* ./

# 根据锁文件选择包管理器安装依赖
RUN if [ -f pnpm-lock.yaml ]; then \
        corepack enable && corepack prepare pnpm@latest --activate && pnpm install --frozen-lockfile; \
    elif [ -f yarn.lock ]; then \
        corepack enable && corepack prepare yarn@latest --activate && yarn install --frozen-lockfile; \
    elif [ -f package-lock.json ]; then \
        npm ci; \
    else \
        npm install; \
    fi

# 拷贝源码并构建
COPY . .
RUN npm run build

# ============ 阶段二：Nginx 托管静态文件 ============
FROM nginx:stable-alpine

# 删除默认 nginx 配置，替换为自定义静态托管配置（含 history 路由回退）
RUN rm /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/conf.d/default.conf

COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
