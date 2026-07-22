# ------------------------------------------------------------------
# Dockerfile
# ------------------------------------------------------------------
# Builds a container image with everything needed to run the
# Velvora AI Support Agent — Python, ffmpeg (if needed later),
# and all project dependencies.
#
# This single image is used for BOTH services (Telegram bot and
# web server) — docker-compose.yml decides which command each
# container actually runs.
# ------------------------------------------------------------------

FROM python:3.11-slim

# ffmpeg included for any future audio processing needs
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (better layer caching —
# only reinstalls if requirements.txt actually changes)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the project
COPY . .

# Default command (overridden per-service in docker-compose.yml)
CMD ["python", "-m", "adapters.telegram_adapter"]