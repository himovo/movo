def normalize_stock_code(company_name: str, ts_code: str | None) -> str | None:
    """Normalize stock code input for downstream tools."""
    if ts_code:
        return ts_code.strip().upper()
    if not company_name:
        return None
    return None
