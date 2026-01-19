FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖和 Chrome
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    wget \
    gnupg \
    unzip \
    curl \
    ca-certificates \
    && mkdir -p /etc/apt/keyrings \
    && wget -q -O /etc/apt/keyrings/google-chrome.asc https://dl.google.com/linux/linux_signing_key.pub \
    && echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/google-chrome.asc] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && apt-get purge -y gcc \
    && apt-get autoremove -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目文件
COPY main.py .
COPY core ./core
COPY util ./util
COPY templates ./templates
COPY static ./static
COPY script ./script

# 创建数据目录
RUN mkdir -p ./data/images ./data/accounts

# 声明数据卷
VOLUME ["/app/data"]

# 默认启动 API 服务
CMD ["python", "-u", "main.py"]