"""Debug snapshot dumper for the presentation pipeline.

Persists per-deck collision-detector snapshots to disk for offline
analysis. Not part of production output.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

_DUMP_ROOT = Path(__file__).resolve().parents[3] / "static" / "debug_snapshots" / "presentation"
_CONTENT_PREVIEW = 40


def _safe_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", str(value or "").strip()) or "unknown"


def _content_preview(text: Any) -> str:
    raw = str(text or "").strip().replace("\n", " ")
    if len(raw) <= _CONTENT_PREVIEW:
        return raw
    return raw[:_CONTENT_PREVIEW] + "…"


def _flatten_block(block: Any, depth: int = 0) -> List[Dict[str, Any]]:
    """Recurse into block children and return a flat list with depth info."""
    style = getattr(block, "style", None) or {}
    style_brief = {}
    if isinstance(style, dict):
        for key in ("color", "background", "background_color", "border_color", "font_size", "font_weight"):
            if key in style and style[key] not in (None, ""):
                style_brief[key] = style[key]
    entry = {
        "depth": depth,
        "id": str(getattr(block, "id", "") or "").strip(),
        "type": str(getattr(block, "type", "") or "").strip(),
        "role": str(getattr(block, "role", "") or "").strip(),
        "container_id": str(getattr(block, "container_id", "") or "").strip(),
        "coordinate_space": str(getattr(block, "coordinate_space", "page") or "page").strip(),
        "x": float(getattr(block, "x", 0.0) or 0.0),
        "y": float(getattr(block, "y", 0.0) or 0.0),
        "w": float(getattr(block, "w", 0.0) or 0.0),
        "h": float(getattr(block, "h", 0.0) or 0.0),
        "z_index": int(getattr(block, "z_index", 0) or 0),
        "content_preview": _content_preview(getattr(block, "content", "")),
        "style_brief": style_brief,
    }
    out = [entry]
    for child in list(getattr(block, "children", None) or []):
        out.extend(_flatten_block(child, depth=depth + 1))
    return out
def _build_collision_dump(
    *,
    blueprint: Any,
    collision_report: Any,
    timestamp_iso: str,
) -> Dict[str, Any]:
    """Build a dump whose per-page verdict comes from the deterministic
    collision detector so the offline reviewer can audit geometry defects."""
    cr_pages_by_id: Dict[str, Any] = {}
    for cp in list(getattr(collision_report, "pages", None) or []):
        cr_pages_by_id[str(getattr(cp, "page_id", "") or "").strip()] = cp

    pages_out: List[Dict[str, Any]] = []
    for page in list(getattr(blueprint, "pages", None) or []):
        page_id = str(getattr(page, "page_id", "") or "").strip()
        blocks_flat: List[Dict[str, Any]] = []
        for block in list(getattr(page, "blocks", None) or []):
            blocks_flat.extend(_flatten_block(block, depth=0))
        cp = cr_pages_by_id.get(page_id)
        defects = [d.to_dict() for d in (getattr(cp, "defects", None) or [])] if cp else []
        pages_out.append({
            "page_id": page_id,
            "page_title": str(getattr(page, "page_title", "") or "").strip(),
            "page_subtitle": str(getattr(page, "page_subtitle", "") or "").strip(),
            "layout_type": str(getattr(page, "layout_type", "") or "").strip(),
            "design_intent": str(getattr(page, "design_intent", "") or "").strip(),
            "block_count": len(blocks_flat),
            "blocks": blocks_flat,
            "collision_qc": {
                "has_issue": bool(defects),
                "defect_count": len(defects),
                "defects": defects,
            },
        })

    return {
        "deck_id": str(getattr(blueprint, "deck_id", "") or "").strip(),
        "phase": "collision_only",
        "timestamp": timestamp_iso,
        "collision_summary": {
            "failed_page_ids": list(getattr(collision_report, "failed_page_ids", None) or []),
            "total_defect_count": int(getattr(collision_report, "total_defect_count", 0) or 0),
            "total_pages": len(pages_out),
            "ok_pages": len(pages_out) - len(list(getattr(collision_report, "failed_page_ids", None) or [])),
        },
        "pages": pages_out,
    }


def _render_collision_markdown(dump: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# Collision-only snapshot")
    lines.append("")
    lines.append(f"- deck_id: `{dump['deck_id']}`")
    lines.append(f"- timestamp: `{dump['timestamp']}`")
    summary = dump["collision_summary"]
    lines.append(
        f"- ok_pages / total: **{summary['ok_pages']} / {summary['total_pages']}**"
    )
    lines.append(f"- failed_page_ids: {summary['failed_page_ids']}")
    lines.append(f"- total_defect_count: {summary['total_defect_count']}")
    lines.append("")

    for page in dump["pages"]:
        pid = page["page_id"]
        cqc = page.get("collision_qc") or {}
        marker = "❌" if cqc.get("has_issue") else "✅"
        lines.append(f"## {marker} {pid} — {page['page_title']}")
        lines.append("")
        lines.append(
            f"- layout: `{page['layout_type']}` · block_count: {page['block_count']}"
        )
        if page.get("design_intent"):
            lines.append(f"- design_intent: {page['design_intent']}")
        defects = list(cqc.get("defects") or [])
        if defects:
            lines.append(f"- collision defects ({len(defects)}):")
            for d in defects:
                if not isinstance(d, dict):
                    continue
                lines.append(
                    f"  - [{d.get('kind', 'other')}] severity={d.get('severity', '?')} "
                    f"block_ids={d.get('block_ids') or []} "
                    f"eaten={d.get('smaller_block_eaten_ratio', '?')} :: {(d.get('note') or '').strip()}"
                )
        lines.append("")
        lines.append("### blocks")
        lines.append("")
        for b in page["blocks"]:
            indent = "  " * b["depth"]
            lines.append(
                f"{indent}- `{b['id'] or '(no-id)'}` type=`{b['type']}` "
                f"role=`{b['role'] or '-'}` container_id=`{b['container_id'] or '-'}` "
                f"rect=({b['x']:.3f},{b['y']:.3f},{b['w']:.3f},{b['h']:.3f}) "
                f"z={b['z_index']}"
                + (f' · "{b["content_preview"]}"' if b["content_preview"] else "")
            )
        lines.append("")
    return "\n".join(lines)


def dump_collision_only_report(
    *,
    blueprint: Any,
    collision_report: Any,
) -> None:
    """Persist a collision-only snapshot of the deck to disk.

    Writes a JSON + Markdown twin into the debug_snapshots directory,
    using the deterministic collision detector's per-page verdict.
    Never raises on I/O failure.
    """
    try:
        _DUMP_ROOT.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        timestamp_iso = datetime.now().isoformat(timespec="seconds")
        deck_id = _safe_id(getattr(blueprint, "deck_id", "unknown"))
        base = f"{deck_id}_{timestamp}_collision_only"
        dump = _build_collision_dump(
            blueprint=blueprint,
            collision_report=collision_report,
            timestamp_iso=timestamp_iso,
        )
        json_path = _DUMP_ROOT / f"{base}.json"
        md_path = _DUMP_ROOT / f"{base}.md"
        json_path.write_text(json.dumps(dump, ensure_ascii=False, indent=2), encoding="utf-8")
        md_path.write_text(_render_collision_markdown(dump), encoding="utf-8")
        logger.info(
            "presentation_collision_dump written deck_id=%s path=%s",
            deck_id,
            json_path,
        )
    except Exception:
        logger.warning(
            "presentation_collision_dump_failed",
            exc_info=True,
        )
