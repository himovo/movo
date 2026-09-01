from __future__ import annotations

import html
import os
import re
import tempfile
from typing import Any, Dict, List, Tuple

from app.utils.markdown_assets import render_markdown_assets
from app.utils.i18n import get_list as i18n_get_list


CODE_BLOCK_RE = re.compile(r"^\s*```([^\n]*)\n([\s\S]*?)```", re.MULTILINE)
IMAGE_RE = re.compile(r"!\[(.*?)\]\((.*?)\)")
HTML_IMG_RE = re.compile(r"<img\b(?P<attrs>[^>]*)/?>", re.IGNORECASE | re.DOTALL)
HTML_ATTR_RE = re.compile(r"""(?P<name>[\w:-]+)\s*=\s*(?P<quote>["'])(?P<value>.*?)(?P=quote)""", re.DOTALL)


def _html_attr(attrs: str, name: str) -> str:
    for match in HTML_ATTR_RE.finditer(attrs or ""):
        if match.group("name").lower() == name.lower():
            return html.unescape(match.group("value") or "").strip()
    return ""


def _normalize_image_src(src: str) -> str:
    value = html.unescape(str(src or "")).strip()
    if value.startswith("<") and value.endswith(">"):
        value = value[1:-1].strip()
    # Markdown allows an optional title after the URL. Keep the URL token only.
    title_match = re.match(r"""^(\S+)\s+["'][^"']*["']\s*$""", value)
    if title_match:
        value = title_match.group(1)
    # Signed OSS URLs sometimes arrive split across lines inside HTML attrs.
    value = re.sub(r"(oss-cn)[\x00-\x20]+(beijing|hangzhou|shanghai|shenzhen|qingdao|zhangjiakou|chengdu|hongkong)\b", r"\1-\2", value, flags=re.IGNORECASE)
    value = re.sub(r"[\x00-\x20]+", "", value)
    return value


def _image_tag(src: str, alt: str = "image") -> str:
    normalized_src = _normalize_image_src(src)
    if not normalized_src:
        return ""
    safe_alt = html.escape(str(alt or "image").strip() or "image", quote=True)
    safe_src = html.escape(normalized_src, quote=True)
    return f'<img alt="{safe_alt}" src="{safe_src}" />'


def _markdown_image_repl(match: re.Match[str]) -> str:
    return _image_tag(match.group(2) or "", match.group(1) or "image")


def _html_image_repl(match: re.Match[str]) -> str:
    attrs = match.group("attrs") or ""
    return _image_tag(_html_attr(attrs, "src"), _html_attr(attrs, "alt") or "image")


def _stash_block(blocks: List[str], content: str) -> str:
    key = f"__BLOCK_{len(blocks)}__"
    blocks.append(content)
    return key


def _markdown_to_html(markdown: str) -> str:
    # DEBUG: Replace literal escape sequences and BOM
    markdown = markdown.lstrip('\ufeff')
    markdown = markdown.replace("\\n", "\n")
    markdown = markdown.replace("\\t", "\t")

    # Ensure an H1 title exists; if missing, promote the first non-empty line.
    if not re.search(r"^#\s+.+", markdown, re.MULTILINE):
        lines = markdown.splitlines()
        title = ""
        rest = []
        for line in lines:
            if not title and line.strip():
                title = line.strip()
            else:
                rest.append(line)
        if title:
            markdown = "# " + title + "\n\n" + "\n".join(rest)
    

    blocks: List[str] = []

    def _code_repl(match: re.Match[str]) -> str:
        lang_line = match.group(1).lower().strip()
        code = match.group(2) or ""
        lang = lang_line.split(' ')[0] if lang_line else ""

        if lang == "mermaid":
            return _stash_block(blocks, f'<div class="mermaid">{html.escape(code)}</div>')
        elif lang == "chart":
            json_data = _parse_chart_data(code)
            return _stash_block(blocks, f'<div class="chart-container" style="position: relative; height:300px; width:100%"><canvas class="chart-block" data-chart="{html.escape(json_data)}"></canvas></div>')
        
        # Normal code block
        code = html.escape(code)
        return _stash_block(blocks, f"<pre><code>{code}</code></pre>")

    def _html_image_block_repl(match: re.Match[str]) -> str:
        tag = _html_image_repl(match)
        return _stash_block(blocks, tag) if tag else ""

    def _markdown_image_block_repl(match: re.Match[str]) -> str:
        tag = _markdown_image_repl(match)
        return _stash_block(blocks, tag) if tag else ""

    text = CODE_BLOCK_RE.sub(_code_repl, markdown)
    text = HTML_IMG_RE.sub(_html_image_block_repl, text)
    text = IMAGE_RE.sub(_markdown_image_block_repl, text)

    lines = text.splitlines()
    
    # State Machine & Page Estimator
    # 0: Cover, 1: TOC, 2: Body
    state = 0
    
    cover_html: List[str] = []
    # TOC buffer is just titles for now, we will render it later
    toc_titles: List[Tuple[str, int]] = [] # (title, page_num)
    body_html: List[str] = []
    has_manual_toc = False
    
    # Track headers seen in potential manual TOC to avoid duplication
    seen_headers_in_toc = set()
    manual_toc_titles: List[str] = []
    
    current_page = 3  # Start content on Page 3
    current_page_height = 0
    PAGE_HEIGHT_LIMIT = 1000 # Abstract units (approx characters/elements)
    
    in_ul = False
    in_ol = False
    in_table = False
    table_rows = []
    
    def get_current_buffer():
        if state == 0: return cover_html
        return body_html

    def close_all(buf):
        close_lists(buf)
        close_table(buf)

    def close_lists(buf):
        nonlocal in_ul, in_ol
        if in_ul:
            buf.append("</ul>")
            in_ul = False
        if in_ol:
            buf.append("</ol>")
            in_ol = False

    def close_table(buf):
        nonlocal in_table, table_rows
        if in_table:
            if table_rows:
                buf.append('<table class="markdown-table">')
                has_sep = False
                if len(table_rows) > 1:
                    sep_line = table_rows[1].strip()
                    if re.match(r"^\|?[:\-\s|]+\|?$", sep_line) and '-' in sep_line:
                        has_sep = True
                
                start_body = 0
                if has_sep:
                    header = table_rows[0]
                    cells = [c.strip() for c in re.split(r'(?<!\\)\|', header.strip().strip('|'))]
                    buf.append('<thead><tr>')
                    for cell in cells:
                        buf.append(f'<th>{html.escape(cell)}</th>')
                    buf.append('</tr></thead>')
                    start_body = 2
                
                buf.append('<tbody>')
                for row_idx in range(start_body, len(table_rows)):
                    row = table_rows[row_idx]
                    cells = [c.strip() for c in re.split(r'(?<!\\)\|', row.strip().strip('|'))]
                    buf.append('<tr>')
                    for cell in cells:
                        buf.append(f'<td>{html.escape(cell)}</td>')
                    buf.append('</tr>')
                buf.append('</tbody></table>')
            in_table = False
            table_rows = []

    for line in lines:
        stripped = line.strip()
        

        # Structure Detection
        toc_tokens = i18n_get_list("toc_heading_variants", "zh") + i18n_get_list("toc_heading_variants", "en")
        # Support "目录", "# 目录", "## 目录"
        toc_pattern = r"^#{0,2}\s*(" + "|".join(re.escape(t) for t in toc_tokens) + r")\s*$"
        if state == 0 and re.match(toc_pattern, stripped, re.IGNORECASE):
             has_manual_toc = True
             state = 1
             close_lists(cover_html)
             continue
        elif re.match(r"^[-*_]{3,}\s*$", stripped):
             if state == 1:
                 state = 2
                 continue
             continue
            
        # Skip processing if we are in TOC state
        if state == 1:
            # If we see something that looks like a header, track it but don't transition yet
            # A manual TOC is usually a list of headers. 
            # We switch to Body (state 2) when we find a horizontal rule (---) 
            # OR when we see a header that we've already tracked as a TOC entry
            header_match = re.match(r"^(?:#{1,3}\s+)?(\d+[.、 ]\s*)?(.+)$", stripped)
            if header_match:
                title = header_match.group(2).strip()
                manual_toc_titles.append(title)
                if title in seen_headers_in_toc:

                    state = 2
                else:
                    seen_headers_in_toc.add(title)
                    continue
            else:
                 continue
                 
         # Failsafe for Cover State (State 0) -> Body
        if state == 0 and (re.match(r"^#{1,3}\s+", stripped) or re.match(r"^\d+[.、 ]", stripped)):
             header_match = re.match(r"^(?:#{1,3}\s+)?(\d+[.、 ]\s*)?(.+)$", stripped)
             if header_match: seen_headers_in_toc.add(header_match.group(2).strip())

             state = 2
             close_lists(cover_html)
             # Fallthrough to process line

        buf = get_current_buffer()
        
        if not stripped:
            close_all(buf)
            # Prevent leading spacers in body
            if state == 2 and not body_html:
                continue
            buf.append("<div class=\"spacer\"></div>")
            continue

        if re.fullmatch(r"__BLOCK_\d+__", stripped):
            close_all(buf)
            buf.append(stripped)
            current_page_height += 420
            continue
        
        # Table Detection
        if '|' in stripped and not in_ul and not in_ol and not stripped.startswith('#'):
             if not in_table:
                 close_lists(buf)
                 in_table = True
             table_rows.append(stripped)
             continue
        elif in_table:
             close_table(buf)

        # Height estimation
        height_cost = len(stripped)
        
        if stripped.startswith("### "):
            close_all(buf)
            buf.append(f"<h3>{html.escape(stripped[4:])}</h3>")
            current_page_height += 50
        elif stripped.startswith("## "):
            close_all(buf)
            # New Section!
            if state == 2:
                 if stripped[3:].strip() in manual_toc_titles:
                     continue
                 if current_page_height > 200:
                     current_page += 1
                     current_page_height = 0
                     buf.append('<div style="page-break-before: always;"></div>')
                 
                 toc_titles.append((stripped[3:], current_page))
            
            buf.append(f"<h2>{html.escape(stripped[3:])}</h2>")
            current_page_height += 80
        elif stripped.startswith("# "):
            close_all(buf)
            # Check if this is a main title and we are in body
            if state == 2:
                 if stripped[2:].strip() in manual_toc_titles:
                     continue
                 toc_titles.append((stripped[2:], current_page))
            buf.append(f"<h1>{html.escape(stripped[2:])}</h1>")
            current_page_height += 100
        elif re.match(r"^\d+[.、]\s+", stripped):
            # Numbered header like "1. 引言"
            close_all(buf)
            title = re.sub(r"^\d+[.、]\s+", "", stripped)
            if state == 2:
                 if title.strip() in manual_toc_titles:
                     continue
                 toc_titles.append((title, current_page))
            buf.append(f"<h2>{html.escape(stripped)}</h2>")
            current_page_height += 80
        elif re.match(r"^[•-]\s+", stripped):
            if not in_ul:
                close_all(buf)
                buf.append("<ul>")
                in_ul = True
            item = re.sub(r"^[•-]\s+", "", stripped)
            buf.append(f"<li>{html.escape(item)}</li>")
            height_cost = len(item) + 20
        elif re.match(r"^\d+\.\s+", stripped):
            if not in_ol:
                close_all(buf)
                buf.append("<ol>")
                in_ol = True
            item = re.sub(r"^\d+\.\s+", "", stripped)
            buf.append(f"<li>{html.escape(item)}</li>")
            height_cost = len(item) + 20
        else:
            close_all(buf)
            escaped = html.escape(stripped)
            escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
            escaped = re.sub(r"\*(.+?)\*", r"<em>\1</em>", escaped)
            
            if state == 0 and not stripped.startswith("#"):
                 buf.append(f"<p class=\"abstract\">{escaped}</p>")
            else:
                 buf.append(f"<p>{escaped}</p>")
        
        # Estimate height for blocks (charts/images)
        # Check if line contains a block key
        if "__BLOCK_" in line:
            current_page_height += 400 # Chart/Image is big
        else:
            current_page_height += height_cost
            
        if current_page_height > PAGE_HEIGHT_LIMIT:
            current_page += 1
            current_page_height = 0

    close_all(body_html)
    
    # Generate TOC HTML
    language = "zh" if re.search(r"[\\u4e00-\\u9fff]", markdown or "") else "en"
    toc_title = i18n_get_list("toc_heading_variants", language)[0]
    toc_html_str = ""
    toc_html_str += f"<h1>{toc_title}</h1>"
    for title, page in toc_titles:
        toc_html_str += f'<h2><span class="toc-title">{html.escape(title)}</span><span class="toc-leader"></span><span class="toc-page-num">{page}</span></h2>'
    
    # Restore blocks and combine structure
    full_html = ""
    if cover_html:
        full_html += f'<div class="cover-page"><div class="cover-content">{"".join(cover_html)}</div></div>'
    
    # Only render TOC when the source markdown explicitly contains a TOC heading.
    if has_manual_toc and toc_titles:
        full_html += f'<div class="toc-page">{toc_html_str}</div>'
    
    if body_html:
        full_html += f'<div class="content-body">{"".join(body_html)}</div>'
        
    for idx, block in enumerate(blocks):
        full_html = full_html.replace(f"__BLOCK_{idx}__", block)
        
    return full_html


def _parse_chart_data(raw: str) -> str:
    """Try to parse YAML-like chart data to JSON."""
    try:
        import json
        # If it's already valid JSON, return as is
        json.loads(raw)
        return raw
    except:
        pass
    
    # Simple YAML-like parser
    result = {}
    lines = raw.strip().splitlines()
    import re
    for line in lines:
        if ':' not in line: continue
        key, val = line.split(':', 1)
        key = key.strip().strip('"\'')
        val = val.strip()
        
        # Try to parse list-like value [1, 2, 3] or ["a", "b"]
        if val.startswith('[') and val.endswith(']'):
            import ast
            try:
                result[key] = ast.literal_eval(val)
            except:
                result[key] = val
        else:
            # Try to parse as int/float
            try:
                if '.' in val: result[key] = float(val)
                else: result[key] = int(val)
            except:
                result[key] = val.strip('"\'')
    
    import json
    return json.dumps(result)


async def generate_pdf_file(markdown_content: str, filename: str = "report.pdf") -> str:
    from playwright.async_api import async_playwright

    if not filename.endswith(".pdf"):
        filename = f"{filename}.pdf"

    html_body = _markdown_to_html(markdown_content)
    
    # Use CDN for Mermaid and Chart.js
    html_doc = f"""
    <html lang="zh-CN">
      <head>
        <meta charset="utf-8" />
        <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@300;400;500;700&display=swap" rel="stylesheet">
        <script src="https://cdn.jsdelivr.net/npm/mermaid@10.9.0/dist/mermaid.min.js"></script>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <style>
            body {{
            font-family: "Noto Sans SC", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
            color: #111827;
            line-height: 1.6;
            font-size: 14px;
            margin: 0;
            padding: 0;
            -webkit-font-smoothing: antialiased;
          }}
          
          /* Page Breaks */
          .cover-page {{
              height: 100vh;
              display: flex;
              align-items: center;
              justify-content: center;
              text-align: center;
              page-break-after: always;
              background: #f9fafb;
          }}
          .toc-page {{
              padding: 40px;
              page-break-after: always;
          }}
          .content-body {{
              padding: 40px;
          }}
          
          /* Typography */
          h1 {{ font-size: 28px; margin: 0 0 16px; font-weight: 700; color: #111; }}
          h2 {{ font-size: 22px; margin: 24px 0 12px; font-weight: 700; border-bottom: 2px solid #e5e7eb; padding-bottom: 8px; color: #374151; }}
          h3 {{ font-size: 18px; margin: 18px 0 10px; font-weight: 700; color: #4b5563; }}
          p {{ margin: 10px 0; text-align: justify; color: #374151; }}
          ul, ol {{ margin: 10px 0 10px 20px; color: #374151; }}
          li {{ margin: 6px 0; }}
          strong {{ font-weight: 700; color: #000; }}
          
          /* Cover Styling */
          .cover-page h1 {{ font-size: 36px; margin-bottom: 30px; color: #000; max-width: 80%; margin-left: auto; margin-right: auto; line-height: 1.4; }}
          .cover-page .abstract {{ font-size: 18px; color: #666; max-width: 600px; margin: 0 auto; line-height: 1.6; }}
          
          /* TOC Styling */
          .toc-page h1 {{ text-align: center; margin-bottom: 40px; font-size: 24px; }}
          .toc-page h2 {{ 
              font-size: 14px; 
              margin: 8px 0; /* Reduced margin */
              font-weight: normal; 
              display: flex; 
              align-items: flex-end; /* Align dots to bottom */
              border-bottom: none; /* No solid line */
              padding: 0;
          }}
          .toc-page .toc-title {{ order: 1; }}
          .toc-page .toc-leader {{ 
              order: 2; 
              flex: 1; 
              border-bottom: 1px dotted #999; 
              margin: 0 8px; 
              position: relative; 
              bottom: 4px; /* Adjust dot position */
          }}
          .toc-page .toc-page-num {{ order: 3; }}
          
          /* Code Blocks */
          pre {{
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            color: #334155;
            padding: 16px;
            border-radius: 8px;
            overflow-x: auto;
            font-size: 14px;
            font-family: monospace;
            margin: 16px 0;
          }}
          
          img, canvas {{
            max-width: 100%;
            margin: 20px 0;
            border-radius: 8px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
          }}
          .chart-container {{ margin: 30px 0; page-break-inside: avoid; }}
          .mermaid {{ margin: 30px 0; display: flex; justify-content: center; page-break-inside: avoid; }}
          .spacer {{ height: 12px; }}

          /* Table Styling */
          table.markdown-table {{
            width: 100%;
            border-collapse: collapse;
            margin: 24px 0;
            font-size: 14px;
            page-break-inside: auto;
          }}
          table.markdown-table th {{
            background: #f3f4f6;
            font-weight: 700;
            text-align: left;
            padding: 12px;
            border: 1px solid #e5e7eb;
            color: #111827;
          }}
          table.markdown-table td {{
            padding: 10px 12px;
            border: 1px solid #e5e7eb;
            text-align: left;
            color: #374151;
            line-height: 1.5;
          }}
          table.markdown-table tr:nth-child(even) {{
            background: #f9fafb;
          }}
          table.markdown-table thead {{
            display: table-header-group;
          }}
        </style>
      </head>
      <body>
        {html_body}
        <script>
          mermaid.initialize({{ startOnLoad: true }});
          
          document.addEventListener('DOMContentLoaded', function() {{
              const charts = document.querySelectorAll('canvas.chart-block');
              charts.forEach(canvas => {{
                  try {{
                      const raw = canvas.dataset.chart;
                      let payload = null;
                      try {{ 
                          payload = JSON.parse(raw); 
                      }} catch(e) {{
                          console.error('JSON parse failed', e);
                          return;
                      }}
                      
                      if (!payload) return;
                      
                      let type = (payload.type || 'line').toLowerCase();
                      if (type === 'column') type = 'bar';
                      
                      let labels = [];
                      let datasets = [];
                      
                      // Chart.js native format
                      if (payload.data && payload.data.labels && payload.data.datasets) {{
                          labels = payload.data.labels;
                          datasets = payload.data.datasets.map(ds => ({{
                              ...ds,
                              borderWidth: ds.borderWidth || 2,
                              fill: ds.fill !== undefined ? ds.fill : (type === 'bar')
                          }}));
                      }} 
                      // Scatter chart with xField/yField format
                      else if (type === 'scatter' && payload.data && payload.xField && payload.yField) {{
                          const dataPoints = payload.data;
                          const seriesField = payload.seriesField;
                          
                          if (seriesField) {{
                              const grouped = new Map();
                              for (const item of dataPoints) {{
                                  const seriesName = item[seriesField];
                                  if (!grouped.has(seriesName)) {{
                                      grouped.set(seriesName, []);
                                  }}
                                  grouped.get(seriesName).push({{
                                      x: item[payload.xField],
                                      y: item[payload.yField]
                                  }});
                              }}
                              
                              datasets = Array.from(grouped.entries()).map(([name, data]) => ({{
                                  label: name,
                                  data: data,
                                  borderWidth: 2
                              }}));
                          }} else {{
                              datasets = [{{
                                  label: payload.title || 'Data',
                                  data: dataPoints.map(item => ({{
                                      x: item[payload.xField],
                                      y: item[payload.yField]
                                  }})),
                                  borderWidth: 2
                              }}];
                          }}
                      }}
                      // Simplified format
                      else {{
                          labels = payload.labels || payload.xAxis || payload.x || [];
                          const series = payload.series || [];
                          if (series.length > 0) {{
                              datasets = series.map((s, idx) => ({{
                                  label: s.name || `Series ${{idx + 1}}`,
                                  data: s.data || [],
                                  borderWidth: 2,
                                  fill: type === 'bar',
                                  backgroundColor: s.backgroundColor || `rgba(${{54 + idx * 50}}, ${{162 - idx * 30}}, 235, 0.2)`,
                                  borderColor: s.borderColor || `rgba(${{54 + idx * 50}}, ${{162 - idx * 30}}, 235, 1)`
                              }}));
                          }} else if (payload.y || payload.data) {{
                              // Handle single series in x/y format
                              datasets = [{{
                                  label: payload.title || 'Data',
                                  data: payload.y || payload.data || [],
                                  borderWidth: 2,
                                  fill: type === 'bar',
                                  backgroundColor: 'rgba(54, 162, 235, 0.2)',
                                  borderColor: 'rgba(54, 162, 235, 1)'
                              }}];
                          }}
                      }}
                      
                      const chartOptions = payload.options || {{ responsive: true, maintainAspectRatio: false }};
                      chartOptions.animation = false; // Disable animation for PDF
                      
                      new Chart(canvas, {{
                          type: type === 'bar' || type === 'line' || type === 'pie' || type === 'scatter' ? type : 'line',
                          data: {{ labels, datasets }},
                          options: chartOptions
                      }});
                  }} catch(e) {{ 
                      console.error('Chart rendering error:', e); 
                  }}
              }});
          }});
        </script>
      </body>
    </html>
    """
    
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    launch_options: Dict[str, Any] = {
        "headless": True,
        "args": [
            "--disable-crash-reporter",
            "--disable-crashpad",
            "--disable-dev-shm-usage",
            "--no-sandbox",
        ],
    }
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(**launch_options)
            page = await browser.new_page()
            await page.set_content(html_doc, wait_until="networkidle")
            # Ensure charts and mermaid diagrams have time to render
            try:
                await page.wait_for_timeout(5000)
            except Exception:
                pass

            await page.emulate_media(media="print")
            await page.pdf(
                path=tmp.name,
                format="A4",
                print_background=True,
                margin={"top": "20mm", "bottom": "20mm", "left": "20mm", "right": "20mm"},
                display_header_footer=True,
                header_template='<div style="font-size: 10px; width: 100%; text-align: right; padding-right: 20mm; color: #999; font-family: sans-serif;">MOVO Report</div>',
                footer_template='<div style="font-size: 10px; width: 100%; text-align: center; color: #999; font-family: sans-serif;"><span class="pageNumber"></span> / <span class="totalPages"></span></div>'
            )
            await browser.close()
    except Exception as e:
        hint = (
            "PDF rendering failed in Playwright runtime. "
            "Please run `playwright install chromium` and ensure host allows headless Chromium execution."
        )
        raise RuntimeError(f"{hint} cause={e}") from e
    return tmp.name


async def render_pdf_from_markdown(markdown_content: str, user_id: str, filename: str = "report.pdf") -> str:
    from app.utils.oss_uploader import AliyunOSSUploader

    rendered_markdown = await render_markdown_assets(markdown_content, user_id)
    file_path = await generate_pdf_file(rendered_markdown, filename)
    uploader = AliyunOSSUploader()
    with open(file_path, "rb") as f:
        content = f.read()
    return uploader.upload_bytes(
        content,
        user_id,
        os.path.basename(file_path),
        content_type="application/pdf",
    )
