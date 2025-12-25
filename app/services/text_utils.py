from __future__ import annotations

ELLIPSIS = "…"
SEPARATORS = ["\n", ".", ";", ":"]


def _find_break_position(snippet: str) -> int | None:
    positions: list[int] = []
    for sep in SEPARATORS:
        idx = snippet.rfind(sep)
        if idx == -1:
            continue
        if sep == "\n":
            positions.append(idx)
        else:
            positions.append(idx + 1)
    if positions:
        return max(positions)
    space_idx = snippet.rfind(" ")
    if space_idx != -1:
        return space_idx
    return None


def truncate_clean(text: str, max_len: int) -> tuple[str, bool]:
    text = text or ""
    text = str(text)
    if max_len <= 0:
        return "", bool(text)
    if len(text) <= max_len:
        return text, False

    snippet = text[:max_len]
    break_pos = _find_break_position(snippet)
    cut_pos = break_pos if break_pos is not None else max_len
    truncated = text[:cut_pos].rstrip()

    if len(truncated) + len(ELLIPSIS) > max_len:
        truncated = truncated[: max_len - len(ELLIPSIS)]

    return f"{truncated}{ELLIPSIS}", True
