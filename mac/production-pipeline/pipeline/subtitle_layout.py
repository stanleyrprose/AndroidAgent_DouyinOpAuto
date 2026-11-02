"""Conservative shared timeline layout for source captions and Burmese overlays."""
from __future__ import annotations
from typing import Any


def source_box_to_output(box: list[float] | None, geometry: dict) -> tuple[int, int, int, int] | None:
    if box is None or len(box) != 4:
        return None
    w, h = geometry['source_dimensions']
    matrix = geometry['source_to_output_affine_matrix']
    scale, ox, oy = matrix[0][0], matrix[0][2], matrix[1][2]
    return (int(box[0] * w * scale + ox), int(box[1] * h * scale + oy),
            int(box[2] * w * scale + ox), int(box[3] * h * scale + oy))


def intersects(a, b, *, margin: int = 24) -> bool:
    return (a[0] < b[2] + margin and a[2] > b[0] - margin and
            a[1] < b[3] + margin and a[3] > b[1] - margin)


def plan_position(event: dict, geometry: dict) -> dict[str, Any]:
    original = source_box_to_output(event.get('ocr_bbox_norm'), geometry)
    candidates = [620, 900] if event.get('role') == 'callout' else [1170, 900, 550]
    for y in candidates:
        rect = (90, y, 990, y + 260)
        if original is None or not intersects(rect, original):
            return {'x': 90, 'y': y, 'collision': False, 'source_box': original}
    return {'x': 90, 'y': candidates[-1], 'collision': True, 'source_box': original}


def plan_timeline(events: list[dict], geometry: dict) -> dict[str, dict]:
    """Global deterministic placements; impossible concurrency is a hard failure.

    A slot is conserved for each overlapping time interval. No source event or
    time range is ever silently dropped, shortened or moved to make room.
    """
    # Avoid the bottom UI; keep distinct blocks at least 260 pixels apart.
    slots = (330, 620, 910, 1200, 1490)
    occupied: list[tuple[float, float, tuple[int, int, int, int]]] = []
    positions = {}
    for event in sorted(events, key=lambda e: (float(e['start']),
                                               e.get('role') != 'primary_subtitle',
                                               e['event_id'])):
        original = source_box_to_output(event.get('ocr_bbox_norm'), geometry)
        selected = None
        for y in (reversed(slots) if event.get('role') == 'primary_subtitle' else slots):
            rect = (90, y, 990, y + 260)
            if original and intersects(rect, original):
                continue
            if any(min(float(event['end']), end) > max(float(event['start']), start)
                   and intersects(rect, previous, margin=0)
                   for start, end, previous in occupied):
                continue
            selected = y
            occupied.append((float(event['start']), float(event['end']), rect))
            break
        if selected is None:
            raise ValueError('BLOCKED_CONCURRENT_SUBTITLE_LAYOUT:' + event['event_id'])
        positions[event['event_id']] = {'x':90,'y':selected,'collision':False,
                                         'source_box':original}
    return positions


def verified_backplate(event: dict) -> bool:
    layout = event.get('layout', {})
    return (layout.get('mode') == 'cover_and_replace'
            and layout.get('opaque_rect_verified') is True
            and len(layout.get('verification_frame_refs', [])) >= 2
            and event.get('ocr_bbox_norm') is not None)
