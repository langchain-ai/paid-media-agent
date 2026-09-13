#!/usr/bin/env bash
# Dependency-only recipe shared by MDA's automatic bake and the standalone Dockerfile.
# Never copy project files or write environment variables into this image.
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends \
  ripgrep jq \
  libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libffi8 libcairo2 libgdk-pixbuf-2.0-0 \
  shared-mime-info fonts-dejavu-core
rm -rf /var/lib/apt/lists/*

python -m pip install --no-cache-dir "weasyprint==70.0" "jinja2==3.1.6"
mkdir -p /workspace/in /workspace/out /workspace/analysis /skills

# A bad recipe fails the bake before MDA switches the deployment to this snapshot.
python - <<'PY'
import jinja2
from weasyprint import HTML

assert jinja2.Template("{{ ready }}").render(ready="ready") == "ready"
assert HTML(string="<p>Paid Media Agent sandbox ready</p>").write_pdf().startswith(b"%PDF-")
PY
rg --version
jq --version
