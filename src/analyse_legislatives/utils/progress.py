import sys
import time
from contextlib import contextmanager
from typing import Callable, TextIO

BAR_WIDTH = 28


def _format_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:4.0f}s"
    minutes, seconds = divmod(int(seconds), 60)
    if minutes < 60:
        return f"{minutes:2d}m{seconds:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours:d}h{minutes:02d}m"


@contextmanager
def progress_bar(
    total: int,
    label: str,
    stream: TextIO | None = None,
    enabled: bool | None = None,
):
    """
    Ouvre une barre et fournit le callable `(fait, total)` qui l'avance.

    `enabled=None` décide seul selon `isatty()` ; passer `True` ou `False` force
    le comportement, ce qui rend le module testable sans terminal.
    """
    stream = sys.stderr if stream is None else stream
    if enabled is None:
        enabled = hasattr(stream, "isatty") and stream.isatty()

    if not enabled:
        yield lambda done, total_=total: None
        return

    started = time.monotonic()
    last_drawn = -1.0

    def draw(done: int, total_: int = total) -> None:
        nonlocal last_drawn
        elapsed = time.monotonic() - started
        final = done >= total_
        # Redessiner à chaque tirage coûterait plus cher que le tirage lui-même
        # sur les boucles rapides, et ferait clignoter le terminal.
        if not final and elapsed - last_drawn < 0.1:
            return
        last_drawn = elapsed

        fraction = 1.0 if total_ <= 0 else min(done / total_, 1.0)
        filled = round(BAR_WIDTH * fraction)
        eta = "" if done == 0 else _format_duration(elapsed * (1 / fraction - 1))
        stream.write(
            f"\r{label} |{'█' * filled}{' ' * (BAR_WIDTH - filled)}| "
            f"{done}/{total_} ({fraction:4.0%}) "
            f"{_format_duration(elapsed)} écoulées"
            + (f", ~{eta} restantes" if eta and not final else "")
            + "  "
        )
        stream.flush()

    try:
        draw(0)
        yield draw
    finally:
        stream.write("\n")
        stream.flush()


ProgressCallback = Callable[[int, int], None]
"""Signature du point d'accroche : `(tirages faits, tirages au total)`."""
