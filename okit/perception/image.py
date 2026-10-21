"""Load images for VLM calls: EXIF-orient, downscale under provider limits, re-encode.

Also returns a sha256 of the original bytes so perception caches key on content,
not filename (participants have been bitten by duplicate images under new names).
"""

from __future__ import annotations

import base64
import hashlib
import io
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel

from okit.types import ImagePart

# Conservative defaults that fit both OpenAI and Anthropic vision limits; tune on the day.
DEFAULT_MAX_EDGE_PX = 1_568
DEFAULT_MAX_BYTES = 4_500_000


class LoadedImage(BaseModel):
    path: str
    sha256: str
    width: int
    height: int
    original_width: int
    original_height: int
    part: ImagePart


class ImageLoadError(Exception):
    pass


def load_image(
    path: str | Path,
    *,
    max_edge_px: int = DEFAULT_MAX_EDGE_PX,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> LoadedImage:
    p = Path(path)
    raw = p.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    try:
        img: Image.Image = Image.open(io.BytesIO(raw))
        img = ImageOps.exif_transpose(img)
    except (UnidentifiedImageError, OSError) as exc:
        raise ImageLoadError(f"{p}: not a readable image ({exc})") from exc

    ow, oh = img.size
    if img.mode not in ("RGB", "L"):
        # Flatten alpha onto white; transparent screenshots otherwise turn black.
        bg = Image.new("RGB", img.size, (255, 255, 255))
        rgba = img.convert("RGBA")
        bg.paste(rgba, mask=rgba.split()[-1])
        img = bg
    img.thumbnail((max_edge_px, max_edge_px), Image.Resampling.LANCZOS)

    quality = 90
    while True:
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        data = buf.getvalue()
        if len(data) <= max_bytes or quality <= 40:
            break
        quality -= 10
    if len(data) > max_bytes:
        raise ImageLoadError(f"{p}: {len(data)} bytes after compression exceeds {max_bytes}")

    return LoadedImage(
        path=str(p),
        sha256=digest,
        width=img.size[0],
        height=img.size[1],
        original_width=ow,
        original_height=oh,
        part=ImagePart(media_type="image/jpeg", data_b64=base64.b64encode(data).decode("ascii")),
    )
