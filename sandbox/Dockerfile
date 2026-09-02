# Reproducible snapshot recipe. Bake stable system dependencies only; mount instructions,
# skills, wiki pages, templates, and workspace content from the repository at run time.
FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ripgrep jq \
    libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libffi-dev libcairo2 libgdk-pixbuf-2.0-0 shared-mime-info fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --extra reports --no-dev --no-install-project

# No secrets, .env files, skills, or wiki content are copied into the image.
ENV PATH="/app/.venv/bin:${PATH}"
CMD ["python", "-c", "print('paid-media-agent sandbox ready')"]
