"""``StdoutNotifier`` — write the rendered digest to a stream (default stdout).

The zero-dependency channel: useful as a dry-run (``AMPERE_NOTIFY=stdout``) to preview exactly what
a real channel would receive, and as a safe default when no push credentials are configured.
"""

from __future__ import annotations

import sys
from typing import TextIO


class StdoutNotifier:
    """A ``Notifier`` that prints the message to an injected text stream."""

    kind = "stdout"

    def __init__(self, stream: TextIO | None = None) -> None:
        self._stream = stream if stream is not None else sys.stdout

    def send(self, text: str) -> None:
        self._stream.write(text + "\n")
        self._stream.flush()
