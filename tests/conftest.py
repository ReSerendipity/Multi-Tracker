"""Pytest bootstrap: put the repository root on sys.path.

The core pipeline modules (``download_bili_following_latest``,
``sync_bilibili_comments_to_feishu``, ``postprocess_bili_videos`` …) live at
the repo root, so tests imported as top-level modules need that path.
Without this conftest, plain ``pytest tests/`` fails with
``ModuleNotFoundError`` and only ``python -m pytest tests/`` works.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
