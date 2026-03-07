# ============================================================
# DocuMind - Dockerfile
# 
# Multi-stage build:
# Stage 1: Build the Angular frontend into static files
# Stage 2: Run the Python backend (serves both API and frontend)
#
# "Multi-stage" means we use one image to BUILD, then copy
# only what we need into a smaller image to RUN.
# This keeps the final image small — no node_modules,
# no build tools, just the app.
# ============================================================

# --- Stage 1: Build Angular frontend ---
# node:20-slim is a lightweight Node.js image
# "AS frontend-builder" names this stage so we can
# reference it later with COPY --from=frontend-builder
FROM node:20-slim AS frontend-builder

# Set working directory inside the container
# Every command after this runs from /app/frontend
WORKDIR /app/frontend

# Copy package files FIRST — Docker layer caching trick
# Docker caches each step as a "layer"
# If package.json hasn't changed since last build,
# Docker skips npm install entirely — saves minutes
COPY frontend/package*.json ./

# Install npm dependencies inside the container
RUN npm install

# NOW copy the rest of the frontend source code
# We do this AFTER npm install so changing a .ts file
# doesn't trigger a full npm install on rebuild
COPY frontend/ ./

# Build Angular for production
# This compiles TypeScript → JavaScript, minifies code,
# and outputs static files (HTML, JS, CSS) to
# dist/frontend/browser/
RUN npx ng build --configuration=production


# --- Stage 2: Python backend ---
# Start fresh with a clean Python image
# "slim" variant is smaller than the full image
# The frontend Stage 1 is discarded — only the built
# files carry over via COPY --from
FROM python:3.13-slim

# Set working directory
WORKDIR /app

# Install system dependencies that some Python packages
# need to compile (like sentence-transformers)
# --no-install-recommends skips optional packages
# rm -rf cleans up the apt cache to save image space
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python packages
# Same caching trick as npm — if requirements.txt
# hasn't changed, this layer is cached
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the Python application code
COPY main.py .
COPY mcp_server.py .

# Copy the built Angular files from Stage 1
# --from=frontend-builder grabs files from the first stage
# These static files get served by FastAPI in production
COPY --from=frontend-builder /app/frontend/dist/frontend/browser ./static

# Create directories for runtime data
# uploads/ stores PDFs, chroma_data/ stores vectors
RUN mkdir -p uploads chroma_data

# Document that this container listens on port 8000
# This doesn't actually open the port — it's metadata
# for other developers and orchestration tools
EXPOSE 8000

# Health check — Docker and Kubernetes use this to know
# if the container is healthy
# --interval=30s: check every 30 seconds
# --timeout=10s: wait up to 10 seconds for a response
# --retries=3: mark unhealthy after 3 consecutive failures
# The command makes an HTTP request to our health endpoint
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

# The command that runs when the container starts
# This is an array format (exec form) — preferred over
# string format because it doesn't run through a shell
# 0.0.0.0 means "listen on ALL network interfaces"
# (localhost only works INSIDE the container)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]