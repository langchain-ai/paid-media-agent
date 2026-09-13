# Optional standalone publish uses the same recipe as MDA's automatic deploy-time bake.
FROM python:3.13-slim
COPY setup.sh /tmp/paid-media-setup.sh
RUN bash /tmp/paid-media-setup.sh && rm /tmp/paid-media-setup.sh
WORKDIR /workspace
