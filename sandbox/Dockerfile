# The model's filesystem in production. Bake only what host-driven rendering needs; skills, wiki
# pages, workspace content, and secrets are uploaded when a sandbox opens, never copied here.
# The sandbox shell does not inherit image PATH changes, so packages go into the system Python.
FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ripgrep jq \
    libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libffi8 libcairo2 libgdk-pixbuf-2.0-0 \
    shared-mime-info fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "weasyprint==68.1" "jinja2==3.1.6"
RUN mkdir -p /workspace/in /workspace/out /workspace/analysis /skills /docs/business-context
WORKDIR /workspace
