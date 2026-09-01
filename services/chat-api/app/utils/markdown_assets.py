from __future__ import annotations
from app.infrastructure.observability.config import log_print

import asyncio
import json
import os
import re
import tempfile
from typing import Any, Dict, List, Tuple

from PIL import Image, ImageDraw, ImageFont

from app.utils.oss_uploader import AliyunOSSUploader


CODE_BLOCK_RE = re.compile(
    r"^[ \t]*(```+)(mermaid|chart)[ \t]*\r?\n(.*?)^[ \t]*\1[ \t]*$",
    re.DOTALL | re.IGNORECASE | re.MULTILINE,
)
RENDER_TIMEOUT_SECONDS = 12


async def render_markdown_assets(markdown: str, user_id: str) -> str:
    # Normalize blocks where language is on the next line:
    # ```\nmermaid\n... -> ```mermaid\n...
    markdown = re.sub(
        r"(```+)\s*\n\s*(mermaid|chart)\s*\n",
        r"\1\2\n",
        markdown,
        flags=re.IGNORECASE,
    )
    blocks = list(CODE_BLOCK_RE.finditer(markdown))
    preview = markdown[:600].replace("\n", "\\n")
    log_print(f"[charts] scan blocks={len(blocks)} len={len(markdown)} preview={preview}")
    if not blocks:
        return markdown
    uploader = AliyunOSSUploader()
    replacements: List[Tuple[str, str]] = []
    for match in blocks:
        block_type = match.group(2).lower()
        block_content = match.group(3).strip()
        # Debug: show detected blocks and size
        # (guarded by OSS env usage; no-op if DEBUG is off)
        # NOTE: use simple print to align with existing DEBUG flag usage in search.py
        # and avoid extra logger dependencies.
        # This will be noisy only when DEBUG=true.
        log_print(f"[charts] detected {block_type} block, length={len(block_content)}")
        try:
            if block_type == "chart":
                image_url = await asyncio.wait_for(
                    _render_chart(block_content, uploader, user_id),
                    timeout=RENDER_TIMEOUT_SECONDS,
                )
            else:
                image_url = await asyncio.wait_for(
                    _render_mermaid(block_content, uploader, user_id),
                    timeout=RENDER_TIMEOUT_SECONDS,
                )
        except Exception:
            image_url = ""
        log_print(f"[charts] render result {block_type}: {'ok' if image_url else 'failed'}")
        if image_url:
            replacements.append((match.group(0), f"![diagram]({image_url})"))
    for original, replacement in replacements:
        markdown = markdown.replace(original, replacement)
    return markdown


async def _render_mermaid(diagram: str, uploader: AliyunOSSUploader, user_id: str) -> str:
    try:
        from playwright.async_api import async_playwright
    except Exception:
        return _render_text_placeholder(diagram, uploader, user_id, "mermaid")

    html = f"""
    <html>
      <head>
        <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
      </head>
      <body>
        <div class="mermaid">
{diagram}
        </div>
        <script>mermaid.initialize({{ startOnLoad: true }});</script>
      </body>
    </html>
    """
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page(viewport={"width": 1200, "height": 800})
            await page.set_content(html, wait_until="networkidle")
            await page.wait_for_timeout(500)
            svg = await page.query_selector("svg")
            if not svg:
                await browser.close()
                return _render_text_placeholder(diagram, uploader, user_id, "mermaid")
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
            await svg.screenshot(path=tmp.name)
            await browser.close()
            _, object_path = uploader.upload_file_with_path(tmp.name, user_id)
            return uploader.sign_url(object_path)
    except Exception:
        return _render_text_placeholder(diagram, uploader, user_id, "mermaid")


async def _render_chart(chart_json: str, uploader: AliyunOSSUploader, user_id: str) -> str:
    try:
        payload = json.loads(chart_json)
    except Exception:
        return _render_text_placeholder(chart_json, uploader, user_id, "chart")

    # Try rendering with Chart.js via Playwright for visual parity with frontend/PDF
    try:
        from playwright.async_api import async_playwright

        html = f"""
        <html>
          <head>
            <meta charset="utf-8" />
            <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
            <style>
              body {{ margin: 0; padding: 0; }}
              #wrap {{ width: 1200px; height: 700px; }}
              canvas {{ width: 1200px !important; height: 700px !important; }}
            </style>
          </head>
          <body>
            <div id="wrap">
              <canvas id="c"></canvas>
            </div>
            <script>
              const payload = {json.dumps(payload)};
              let type = (payload.type || 'line').toLowerCase();
              if (type === 'column') type = 'bar';
              if (type === 'radar') type = 'line';
              let labels = [];
              let datasets = [];

              if (payload.data && payload.data.labels && payload.data.datasets) {{
                labels = payload.data.labels;
                datasets = payload.data.datasets.map(ds => ({{
                  ...ds,
                  borderWidth: ds.borderWidth || 2,
                  fill: ds.fill !== undefined ? ds.fill : (type === 'bar')
                }}));
              }} else if (type === 'scatter' && payload.data && payload.xField && payload.yField) {{
                const dataPoints = payload.data;
                const seriesField = payload.seriesField;
                if (seriesField) {{
                  const grouped = new Map();
                  for (const item of dataPoints) {{
                    const seriesName = item[seriesField];
                    if (!grouped.has(seriesName)) grouped.set(seriesName, []);
                    grouped.get(seriesName).push({{ x: item[payload.xField], y: item[payload.yField] }});
                  }}
                  datasets = Array.from(grouped.entries()).map(([name, data]) => ({{
                    label: name, data, borderWidth: 2
                  }}));
                }} else {{
                  datasets = [{{
                    label: payload.title || 'Data',
                    data: dataPoints.map(item => ({{
                      x: item[payload.xField], y: item[payload.yField]
                    }})),
                    borderWidth: 2
                  }}];
                }}
              }} else {{
                labels = payload.labels || payload.xAxis || payload.x || [];
                const series = payload.series || [];
                if (series.length > 0) {{
                  datasets = series.map((s, idx) => ({{
                    label: s.name || `Series ${{idx + 1}}`,
                    data: s.data || [],
                    borderWidth: 2,
                    fill: type === 'bar'
                  }}));
                }} else if (payload.y || payload.data) {{
                  datasets = [{{
                    label: payload.title || 'Data',
                    data: payload.y || payload.data || [],
                    borderWidth: 2,
                    fill: type === 'bar'
                  }}];
                }}
              }}

              const options = payload.options || {{ responsive: false, maintainAspectRatio: false }};
              // Ensure y-axis ticks/grid are visible for bar/line charts
              if (type === 'bar' || type === 'line') {{
                options.scales = options.scales || {{}};
                options.scales.y = options.scales.y || {{}};
                options.scales.y.ticks = options.scales.y.ticks || {{}};
                options.scales.y.ticks.display = true;
                options.scales.y.grid = options.scales.y.grid || {{}};
                options.scales.y.grid.display = true;
              }}
              new Chart(document.getElementById('c').getContext('2d'), {{
                type: ['bar','line','pie','scatter'].includes(type) ? type : 'line',
                data: {{ labels, datasets }},
                options
              }});
            </script>
          </body>
        </html>
        """

        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page(viewport={"width": 1200, "height": 700})
            await page.set_content(html, wait_until="networkidle")
            await page.wait_for_timeout(1200)
            canvas = await page.query_selector("#c")
            if canvas:
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
                await canvas.screenshot(path=tmp.name)
                await browser.close()
                _, object_path = uploader.upload_file_with_path(tmp.name, user_id)
                return uploader.sign_url(object_path)
            await browser.close()
    except Exception:
        pass

    chart_type = (payload.get("type") or "line").lower()
    if chart_type == "radar":
        chart_type = "line"
    title = payload.get("title") or "Chart"
    labels = payload.get("labels") or []
    series = payload.get("series") or []

    # Normalize common formats into labels/series
    data_block = payload.get("data")
    if isinstance(data_block, dict):
        if data_block.get("labels") and data_block.get("datasets"):
            labels = data_block.get("labels") or labels
            series = []
            for ds in data_block.get("datasets") or []:
                series.append({"name": ds.get("label") or title, "data": ds.get("data") or []})
        if data_block.get("labels") and data_block.get("values"):
            labels = data_block.get("labels") or labels
            series = [{"name": title, "data": data_block.get("values") or []}]
        if data_block.get("values") and isinstance(data_block.get("values"), list):
            if data_block.get("values") and isinstance(data_block.get("values")[0], dict):
                labels = [v.get("category") for v in data_block.get("values") if v.get("category") is not None]
                series = [{"name": title, "data": [v.get("value", 0) for v in data_block.get("values")]}]
    if isinstance(data_block, list) and payload.get("xField") and payload.get("yField"):
        labels = [str(item.get(payload["xField"])) for item in data_block]
        y_fields = payload.get("yField")
        if isinstance(y_fields, list):
            series = [{"name": f, "data": [item.get(f, 0) for item in data_block]} for f in y_fields]
        else:
            series = [{"name": title, "data": [item.get(y_fields, 0) for item in data_block]}]

    width, height = 1200, 700
    margin = 80
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)
    # Try to load a font that supports CJK; fallback to default
    font = ImageFont.load_default()
    for font_path in (
        "/System/Library/Fonts/PingFang.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/STHeiti Light.ttc",
    ):
        if os.path.exists(font_path):
            try:
                font = ImageFont.truetype(font_path, 18)
                break
            except Exception:
                continue

    draw.text((margin, 20), title, fill="black", font=font)

    # Normalize unsupported chart types to bar/line if possible
    if chart_type in {"radar"} and labels and series:
        chart_type = "bar"

    if chart_type in {"line", "bar"} and labels and series:
        max_val = max((max(s.get("data", []) or [0]) for s in series), default=1)
        plot_w = width - 2 * margin
        plot_h = height - 2 * margin
        origin = (margin, height - margin)
        draw.line([origin, (margin, margin)], fill="black", width=2)
        draw.line([origin, (width - margin, height - margin)], fill="black", width=2)

        count = len(labels)
        step_x = plot_w / max(count, 1)
        colors = ["#2563eb", "#16a34a", "#dc2626", "#f59e0b"]

        for idx, s in enumerate(series):
            data = s.get("data", [])
            points = []
            for i, val in enumerate(data):
                x = margin + i * step_x + step_x / 2
                y = height - margin - (val / max_val) * plot_h
                points.append((x, y))
            if chart_type == "line" and len(points) >= 2:
                draw.line(points, fill=colors[idx % len(colors)], width=3)
                for p in points:
                    draw.ellipse((p[0] - 3, p[1] - 3, p[0] + 3, p[1] + 3), fill=colors[idx % len(colors)])
            if chart_type == "bar":
                bar_w = step_x * 0.6
                for p in points:
                    draw.rectangle((p[0] - bar_w / 2, p[1], p[0] + bar_w / 2, height - margin), fill=colors[idx % len(colors)])

        for i, label in enumerate(labels):
            x = margin + i * step_x + step_x / 2
            draw.text((x - 10, height - margin + 10), str(label), fill="black", font=font)

    elif chart_type == "scatter" and payload.get("data", {}).get("datasets"):
        datasets = payload.get("data", {}).get("datasets") or []
        # Collect all points for scaling
        points_all = []
        for ds in datasets:
            for pt in ds.get("data", []) or []:
                if isinstance(pt, dict) and "x" in pt and "y" in pt:
                    points_all.append((pt["x"], pt["y"]))
        if points_all:
            min_x = min(p[0] for p in points_all)
            max_x = max(p[0] for p in points_all)
            min_y = min(p[1] for p in points_all)
            max_y = max(p[1] for p in points_all)
            # Avoid zero range
            if max_x == min_x:
                max_x += 1
            if max_y == min_y:
                max_y += 1
            plot_w = width - 2 * margin
            plot_h = height - 2 * margin
            origin = (margin, height - margin)
            draw.line([origin, (margin, margin)], fill="black", width=2)
            draw.line([origin, (width - margin, height - margin)], fill="black", width=2)
            colors = ["#2563eb", "#16a34a", "#dc2626", "#f59e0b"]
            for idx, ds in enumerate(datasets):
                for pt in ds.get("data", []) or []:
                    if not isinstance(pt, dict):
                        continue
                    x_val = pt.get("x")
                    y_val = pt.get("y")
                    if x_val is None or y_val is None:
                        continue
                    x = margin + ((x_val - min_x) / (max_x - min_x)) * plot_w
                    y = height - margin - ((y_val - min_y) / (max_y - min_y)) * plot_h
                    draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill=colors[idx % len(colors)])
        else:
            draw.text((margin, margin + 40), "Chart data missing or invalid.", fill="red", font=font)

    elif chart_type == "pie" and series:
        data = series[0].get("data", [])
        total = sum(data) or 1
        start = 0
        colors = ["#2563eb", "#16a34a", "#dc2626", "#f59e0b"]
        box = (margin, margin, width - margin, height - margin)
        for idx, val in enumerate(data):
            end = start + (val / total) * 360
            draw.pieslice(box, start=start, end=end, fill=colors[idx % len(colors)])
            start = end
    else:
        draw.text((margin, margin + 40), "Chart data missing or invalid.", fill="red", font=font)

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    img.save(tmp.name, format="PNG")
    _, object_path = uploader.upload_file_with_path(tmp.name, user_id)
    return uploader.sign_url(object_path)


def _render_text_placeholder(content: str, uploader: AliyunOSSUploader, user_id: str, title: str) -> str:
    width, height = 1200, 700
    img = Image.new("RGB", (width, height), "#f8fafc")
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()
    draw.text((40, 30), f"{title.upper()} PLACEHOLDER", fill="#111827", font=font)
    preview = content[:600] + ("..." if len(content) > 600 else "")
    draw.text((40, 80), preview, fill="#374151", font=font)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    img.save(tmp.name, format="PNG")
    _, object_path = uploader.upload_file_with_path(tmp.name, user_id)
    return uploader.sign_url(object_path)
