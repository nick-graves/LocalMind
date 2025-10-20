def cap_rows(items, max_rows: int):
    return items[:max_rows] if isinstance(items, list) else items