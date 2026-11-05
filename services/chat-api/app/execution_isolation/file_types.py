"""File types eligible for user-facing sandbox delivery."""

DOCUMENT_OUTPUT_EXTS = frozenset({".docx", ".pdf", ".xlsx", ".pptx", ".txt", ".md", ".json", ".csv"})
IMAGE_OUTPUT_EXTS = frozenset({".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"})
ALLOWED_OUTPUT_EXTS = DOCUMENT_OUTPUT_EXTS | IMAGE_OUTPUT_EXTS
