FROM python:3.12-slim

# Install system dependencies & Go toolchain
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    ca-certificates \
    golang-go \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy project files
COPY pyproject.toml README.md ./
COPY curlcommander ./curlcommander
COPY packaging ./packaging

# Install Python package with optional extras
RUN pip install --no-cache-dir -e ".[browser,oob,recon]"

# Install Playwright Chromium browser
RUN python -m playwright install --with-deps chromium

ENTRYPOINT ["curlcmd"]
CMD ["--help"]
