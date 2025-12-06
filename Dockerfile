FROM python:3.12-slim

# Install system dependencies (poppler-utils for pdf2image)
RUN apt-get update && \
    apt-get install -y poppler-utils && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy project files
COPY pyproject.toml uv.lock ./

# Install uv and dependencies
RUN pip install --no-cache-dir uv && \
    uv sync --frozen --no-dev

# Copy application code
COPY . .

# Make start script executable
COPY start.sh ./
RUN chmod +x start.sh

EXPOSE 8000

# Run both web + worker
CMD ["./start.sh"]