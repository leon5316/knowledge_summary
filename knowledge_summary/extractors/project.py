"""目标收集：单文件或项目文件夹的递归扫描与过滤。"""
from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import List, Tuple

from . import supported_extensions
from ..models import Document  # noqa: F401


class CollectError(Exception):
    pass


def collect_files(target: str, cfg) -> Tuple[Path, List[Path]]:
    """返回 (源根目录, 待解析文件列表)。

    - target 为文件：根目录取其所在目录。
    - target 为文件夹：递归扫描，应用忽略目录 / glob 模式 / 大小限制 / 扩展名过滤。
    """
    target_path = Path(target).resolve()
    if not target_path.exists():
        raise CollectError(f"目标不存在: {target_path}")

    ignore_dirs = set(cfg.get("general", "ignore_dirs", []) or [])
    ignore_patterns = cfg.get("general", "ignore_patterns", []) or []
    max_bytes = float(cfg.get("general", "max_file_size_mb", 20)) * 1024 * 1024
    treat_unknown = cfg.get("general", "treat_unknown_as_text", False)
    exts = supported_extensions()

    if target_path.is_file():
        root = target_path.parent
        return root, [target_path]

    root = target_path
    files: List[Path] = []
    skipped = {"unknown_ext": 0, "too_large": 0, "ignored": 0}

    for dirpath, dirnames, filenames in Path(root).walk():
        dirnames[:] = [d for d in dirnames if d not in ignore_dirs]
        for name in filenames:
            fp = Path(dirpath) / name
            try:
                rel = fp.relative_to(root).as_posix()
            except ValueError:
                rel = name
            if any(fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(name, pat) for pat in ignore_patterns):
                skipped["ignored"] += 1
                continue
            try:
                if fp.stat().st_size > max_bytes:
                    skipped["too_large"] += 1
                    continue
            except OSError:
                continue
            ext = fp.suffix.lower().lstrip(".")
            if ext not in exts and not treat_unknown:
                skipped["unknown_ext"] += 1
                continue
            files.append(fp)

    files.sort(key=lambda p: p.relative_to(root).as_posix())
    return root, files
