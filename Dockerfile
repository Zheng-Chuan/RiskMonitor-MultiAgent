FROM python:3.13-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    default-libmysqlclient-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# 先复制依赖清单以利用构建缓存
COPY requirements.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt
 
# 复制应用代码
COPY main.py .
COPY src ./src
COPY .env* ./

# 暴露 MCP Server 端口(可选; 未来可能用于 HTTP/可观测性等场景)
# MCP 通常走 stdio, 这里保留端口便于扩展
EXPOSE 8000

# 设置环境变量
ENV PYTHONUNBUFFERED=1

# 启动 MCP Server
CMD ["python", "main.py"]
