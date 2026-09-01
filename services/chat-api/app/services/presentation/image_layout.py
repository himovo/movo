from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageOps


def crop_image_bytes_to_aspect(image_bytes: bytes, *, target_width: int, target_height: int) -> bytes:
    """Center-crop an image to the target aspect ratio without stretching it."""
    if not image_bytes or target_width <= 0 or target_height <= 0:
        return image_bytes
    with Image.open(BytesIO(image_bytes)) as source:
        image = ImageOps.exif_transpose(source).convert("RGBA")
        target_ratio = float(target_width) / float(target_height)
        source_ratio = float(image.width) / float(max(1, image.height))
        if source_ratio > target_ratio:
            crop_width = max(1, round(image.height * target_ratio))
            left = max(0, (image.width - crop_width) // 2)
            image = image.crop((left, 0, left + crop_width, image.height))
        elif source_ratio < target_ratio:
            crop_height = max(1, round(image.width / target_ratio))
            top = max(0, (image.height - crop_height) // 2)
            image = image.crop((0, top, image.width, top + crop_height))
        output = BytesIO()
        image.save(output, format="PNG", optimize=True)
        return output.getvalue()


__all__ = ["crop_image_bytes_to_aspect"]
