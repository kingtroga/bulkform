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
RUN pip install uv && \
    uv sync --frozen

# Copy application code
COPY . .

# Expose port (Render will override with $PORT)
EXPOSE 8000

# Start command
CMD uv run uvicorn app:app --host 0.0.0.0 --port $PORT