# PPT Image-Native Visual PoC

This directory is intentionally isolated from the production presentation pipeline.

## Layout-first PoC (recommended next experiment)

This is the newer route for avoiding unstable text-removal/editing:

1. `gpt-5.4` plans editable text/chart zones from `slide_schema.json`.
2. `gpt-image-2` generates a no-text background `B` with empty reserved containers.
3. The script overlays editable PowerPoint text/chart objects using the same layout plan.
4. The script writes a visual `comparison.html` and an editable `layout_first_poc.pptx`.

Important: in API mode, `B` is treated as the image model output. The script only normalizes its size before overlaying editable objects; it does not draw slide-specific decorative panels, icons, dividers, or other visual shell elements onto `B`.

The layout planner is also schema-driven: `gpt-5.4` plans coordinates, alignment, font size, font weight, color, line breaks, and optional spans for each schema text slot. The script only validates that text content still matches `slide_schema.json`; it does not apply hard-coded cover/title/subtitle rules.

`quality_warnings` in the plan JSON are diagnostics only. They are not used as a second repair prompt for image generation; the planner prompt is written so the first layout plan should already include a complete composition contract.

Dry run:

```bash
cd backend
python tests/ppt_image_edit_poc/run_layout_first_poc.py --mode dry-run --max-slides 1
```

API run:

```bash
cd backend
python tests/ppt_image_edit_poc/run_layout_first_poc.py --mode api --max-slides 1
```

Optional planner overrides:

```bash
python tests/ppt_image_edit_poc/run_layout_first_poc.py --mode api --max-slides 1 \
  --planner-model gpt-5.4 \
  --planner-endpoint "https://your-resource.openai.azure.com/openai/responses?api-version=2025-04-01-preview"
```

Outputs are written to `runs/<timestamp>_layout_first/`:

- `<slide>_layout_plan.json`: GPT-5.4 layout plan.
- `<slide>_background_prompt.txt`: prompt sent to `gpt-image-2`.
- `<slide>_B.png`: no-text image background.
- `<slide>_C_preview.png`: background plus editable overlay preview.
- `planned_slide_schema.json`: schema after applying planned coordinates/styles.
- `layout_first_poc.pptx`: editable PPTX.
- `comparison.html`: side-by-side visual inspection page.

The older A-to-B flow below is retained for comparison, but it is not the recommended path when image edit or local inpaint creates visible patch artifacts.

## A-to-B text-removal PoC (legacy experiment)

It validates:

1. Generate full slide visual draft A from a structured slide schema.
2. Use VLM only to infer text placement/style, not content.
3. Build a text mask from inferred regions.
4. Edit A into no-text background B with image edit API (fallback to local inpaint on failures).
5. Generate a PPTX and comparison HTML using B as the slide background and editable PPT objects on top.

## Environment

Add the image API key to `backend/.env`:

```env
AZURE_IMAGE_OPENAI_API_KEY=...
```

The script also reads:

```env
AZURE_IMAGE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_IMAGE_DEPLOYMENT_NAME=gpt-image-2
AZURE_IMAGE_GENERATION_API_STYLE=deployments
AZURE_IMAGE_OPENAI_API_VERSION=2024-02-01
AZURE_IMAGE_EDIT_API_STYLE=v1
AZURE_IMAGE_EDIT_API_VERSION=2024-02-01
AZURE_IMAGE_QUALITY=low
AZURE_IMAGE_SIZE=1536x864
AZURE_IMAGE_MAX_RETRIES=5
AZURE_IMAGE_RETRY_BASE_SECONDS=1.5
AZURE_IMAGE_RETRY_MAX_SECONDS=30
AZURE_IMAGE_HTTP_READ_TIMEOUT=600
AZURE_IMAGE_HTTP_KEEPALIVE=0
AZURE_IMAGE_EDIT_AUTH_STYLE=api-key
AZURE_IMAGE_EDIT_IMAGE_FIELD=image[]
AZURE_IMAGE_EDIT_INCLUDE_MODEL=true
# Optional switches; omitted by default to match the Azure curl example:
# AZURE_IMAGE_EDIT_INCLUDE_SIZE=true
# AZURE_IMAGE_EDIT_INCLUDE_QUALITY=true
# AZURE_IMAGE_EDIT_INCLUDE_OUTPUT_FORMAT=true
# AZURE_IMAGE_EDIT_INCLUDE_N=true
# For v1 edit routes this defaults to true, because transparent mask pixels are treated as edit area.
# For deployment-style curl compatibility this can be set to false.
# AZURE_IMAGE_EDIT_CONVERT_MASK_ALPHA=true
```

Notes:

- The script uses operation-specific Azure image endpoints. For generation, use the version provided by ops, for example `/openai/deployments/{deployment}/images/generations?api-version=2024-02-01`.
- Image edits support two tested shapes. For deployment route compatibility, use the Azure curl shape: `Authorization: Bearer`, multipart fields `image`, `mask`, and `prompt`. For v1 route compatibility, use `api-key`, multipart field `image[]`, and include `model=gpt-image-2`.
- `1536x864` is valid for `gpt-image-2` because its width/height are divisible by 16, total pixels are in range, and aspect ratio is between 1:2 and 2:1. Older GPT Image deployments may only support `1024x1024`, `1024x1536`, and `1536x1024`.
- The edit request intentionally omits optional `model`, `size`, `quality`, `output_format`, and `n` unless the corresponding `AZURE_IMAGE_EDIT_INCLUDE_*` switch is enabled.
- For v1 edit routes, the script converts the visible white-on-transparent `*_mask.png` into `*_mask_api.png`, where only the text removal area is transparent. This prevents accidentally asking the model to edit the whole slide background.
- In edit mode the mask is guidance for text removal; the prompt describes the desired final image and asks the model to preserve all non-text visual elements.
- If edit API fails, script falls back to local inpaint for B.
- Dated `api-version` and `deployments` path settings are no longer required for this PoC.

Install local inpaint dependency in your venv:

```bash
pip install opencv-python-headless
```

## Run

Dry run, no external API calls:

```bash
cd backend
python tests/ppt_image_edit_poc/run_poc.py --mode dry-run
```

API mode:

```bash
cd backend
python tests/ppt_image_edit_poc/run_poc.py --mode api
```

Choose VLM backend by CLI params:

```bash
# qwen (default in auto)
python tests/ppt_image_edit_poc/run_poc.py --mode api --vlm-provider qwen

# gpt-5.4 (Azure Responses)
python tests/ppt_image_edit_poc/run_poc.py --mode api --vlm-provider gpt54
```

Optional overrides:

```bash
python tests/ppt_image_edit_poc/run_poc.py --mode api --vlm-provider gpt54 \
  --vlm-model gpt-5.4 \
  --vlm-endpoint "https://your-resource.openai.azure.com/openai/responses?api-version=2025-04-01-preview"
```

Generation-only smoke test, one slide, no VLM/mask/edit/PPTX:

```bash
cd backend
python tests/ppt_image_edit_poc/run_poc.py --mode api --stage generate-only --max-slides 1
```

Edit-only smoke test, reusing an existing A image and mask without rerunning generation/VLM:

```bash
cd backend
python tests/ppt_image_edit_poc/run_poc.py --mode api --stage edit-only \
  --edit-image tests/ppt_image_edit_poc/runs/20260520_162624/cover_A.png \
  --edit-mask tests/ppt_image_edit_poc/runs/20260520_162624/cover_mask.png
```

If `--edit-image` is omitted, the script uses the latest `runs/*/cover_A.png` and its sibling `cover_mask.png`. `edit-only` does not fall back to local inpaint, so it is the fastest way to verify whether the Azure image edit endpoint is actually available.

Auto mode uses API mode only when `AZURE_IMAGE_OPENAI_API_KEY` is present:

```bash
cd backend
python tests/ppt_image_edit_poc/run_poc.py
```

Outputs are written under `backend/tests/ppt_image_edit_poc/runs/<timestamp>/`.
Open `comparison.html` to inspect A, mask, B, inferred layout, and the PPTX link.

## Optional: Test VLM with Azure Responses (`gpt-5.4`)

Use a dedicated script to test multimodal OCR/style extraction via Azure Responses API:

```env
AZURE_VLM_GPT54_ENDPOINT=https://your-resource.openai.azure.com/openai/responses?api-version=2025-04-01-preview
AZURE_VLM_GPT54_MODEL=gpt-5.4
AZURE_VLM_GPT54_API_KEY=...
```

Run:

```bash
cd backend
python tests/ppt_image_edit_poc/run_vlm_gpt54.py --slide-id cover


```

# Qwen
  python tests/ppt_image_edit_poc/run_poc.py --mode api --stage full --max-slides 1 --vlm-provider qwen

  # GPT-5.4 (Azure Responses)
  python tests/ppt_image_edit_poc/run_poc.py --mode api --stage full --max-slides 1 --vlm-provider gpt54

Notes:

- `--image` not provided: script uses latest `runs/*/cover_A.png`.
- Raw API response, extracted text, and parsed layout JSON are saved under a new `runs/<timestamp>_gpt54/` folder.
- OCR schema uses `text_slots + text_lines + text_spans` to preserve mixed styles within one line.
- OCR style now includes `font_family_hint` (`sans|serif|mono`) and `font_weight_value` (`100..900`) for better cross-language font restoration.
- `text_spans` now supports `char_start/char_end` (0-based, end-exclusive) to keep spaces/punctuation fidelity when reconstructing line text.
