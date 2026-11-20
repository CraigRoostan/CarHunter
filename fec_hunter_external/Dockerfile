# Playwright's own image: Chromium and its system libraries are already installed, which
# is what makes the browser collector deployable without a build step of its own.
FROM mcr.microsoft.com/playwright/python:v1.65.2-noble

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# The SQLite store lives on a volume so the seen-listings survive redeploys.
ENV HUNTER_DB=/app/data/hunter.sqlite3
ENV BROWSER_HEADLESS=true
ENV PYTHONUNBUFFERED=1


# The loop rewrites /app/data/collector.heartbeat at the start of every cycle. A file
# older than fifteen minutes means the process is alive but stuck, so the orchestrator
# restarts it instead of leaving a silent collector running.
HEALTHCHECK --interval=60s --timeout=5s --start-period=120s --retries=3 \
  CMD python -c "import os,sys,time; p='/app/data/collector.heartbeat'; sys.exit(0 if os.path.exists(p) and time.time()-os.path.getmtime(p) < 900 else 1)"

CMD ["python", "run.py"]