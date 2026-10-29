from typing import Any


def paginate(items: list[Any], page: int, size: int) -> dict[str, Any]:
    page = max(page, 1)
    start = (page - 1) * size
    chunk = items[start : start + size]
    return {"items": chunk, "page": page, "pages": page_count(len(items), size)}


def page_count(total: int, size: int) -> int:
    return max(1, -(-total // size))
