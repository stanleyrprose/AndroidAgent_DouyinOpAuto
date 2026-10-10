"""Conservative 1080x1920 layout selection for Chinese hard captions + Myanmar."""
from __future__ import annotations

from typing import Any


def source_box_to_output(box: list[float] | None, geometry: dict) -> tuple[int, int, int, int] | None:
    if box is None or len(box) != 4:
        return None
    w, h = geometry["source_dimensions"]
    matrix = geometry["source_to_output_affine_matrix"]
    scale, ox, oy = matrix[0][0], matrix[0][2], matrix[1][2]
    x0 = int(box[0] * w * scale + ox)
    y0 = int(box[1] * h * scale + oy)
    x1 = int(box[2] * w * scale + ox)
    y1 = int(box[3] * h * scale + oy)
    return (x0, y0, x1, y1)


def intersects(a: tuple[int, int, int, int], b: tuple[int, int, int, int],
               *, margin: int = 24) -> bool:
    return (a[0] < b[2] + margin and a[2] > b[0] - margin and
            a[1] < b[3] + margin and a[3] > b[1] - margin)


def plan_position(event: dict, geometry: dict) -> dict[str, Any]:
    """Position defaults away from TikTok bottom controls and original hard text."""
    original = source_box_to_output(event.get("ocr_bbox_norm"), geometry)
    candidates = [620, 900] if event.get("role") == "callout" else [1170, 900, 550]
    for y in candidates:
        rect = (90, y, 990, y + 260)
        if original is None or not intersects(rect, original):
            return {"x": 90, "y": y, "collision": False, "source_box": original}
    return {"x": 90, "y": candidates[-1], "collision": True, "source_box": original}


def verified_backplate(event: dict) -> bool:
    layout = event.get("layout", {})
    return (layout.get("mode") == "cover_and_replace"
            and layout.get("opaque_rect_verified") is True
            and len(layout.get("verification_frame_refs", [])) >= 2
            and event.get("ocr_bbox_norm") is not None)
