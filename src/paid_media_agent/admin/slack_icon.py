"""A bounded, fixed-path Slack icon upload. User filenames never become filesystem paths."""

from __future__ import annotations

import base64
import io
import os
import tempfile
from pathlib import Path

from PIL import Image, UnidentifiedImageError
from PIL.PngImagePlugin import PngImageFile

from paid_media_agent.deployment import SLACK_ICON_FILENAME

MAX_ICON_BYTES = 1024 * 1024


def icon_path(root: Path) -> Path:
    directory = root / "channels"
    path = directory / SLACK_ICON_FILENAME
    if directory.is_symlink() or path.is_symlink():
        raise ValueError("Slack icon must be a file inside the project's channels directory")
    return path


def icon_data_url(root: Path) -> str:
    path = icon_path(root)
    with path.open("rb") as source:
        data = source.read(MAX_ICON_BYTES + 1)
    if len(data) > MAX_ICON_BYTES:
        raise ValueError("Slack icon must be at most 1 MB")
    return "data:image/png;base64," + base64.b64encode(data).decode("ascii")


def save_icon(root: Path, data: bytes) -> None:
    if len(data) > MAX_ICON_BYTES:
        raise ValueError("Choose a PNG no larger than 1 MB")
    try:
        with Image.open(io.BytesIO(data)) as image:
            if not isinstance(image, PngImageFile) or image.size != (512, 512) or image.is_animated:
                raise ValueError("Choose a still 512 × 512 PNG")
            image.verify()
        with Image.open(io.BytesIO(data)) as image:
            image.load()
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        raise ValueError("Choose a valid 512 × 512 PNG") from exc
    path = icon_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    staging: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".png", delete=False) as dest:
            staging = Path(dest.name)
            dest.write(data)
        os.replace(staging, path)
    finally:
        if staging is not None:
            staging.unlink(missing_ok=True)
