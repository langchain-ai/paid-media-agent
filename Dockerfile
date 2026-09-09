# Self-hosted API (`paid-media-agent serve`) with the rich Slack transports. Pango and Cairo are
# included so PDF reports render here. No .env is copied; pass secrets as environment variables
# or a mounted file. Managed Deep Agents (`mda deploy .`) is the one-command alternative.
FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libffi8 libcairo2 libgdk-pixbuf-2.0-0 \
    shared-mime-info fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv
WORKDIR /app
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
RUN uv sync --frozen --no-dev --extra self-host --extra slack --extra reports
COPY instructions.md ./
COPY skills ./skills
COPY config/accounts.example.toml config/write-policy.example.toml ./config/
RUN mkdir -p workspace/in workspace/out workspace/analysis workspace/logs

ENV PATH="/app/.venv/bin:${PATH}" PAID_MEDIA_API_HOST=0.0.0.0 PAID_MEDIA_API_PORT=8080
EXPOSE 8080
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health')"
CMD ["paid-media-agent", "serve"]
