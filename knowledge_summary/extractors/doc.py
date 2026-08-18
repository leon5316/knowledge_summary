"""旧版 Word .doc 解析器：依赖系统工具（antiword 或 LibreOffice）。"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from ..models import Document
from .base import Extractor, ExtractorError


class DocExtractor(Extractor):
    extensions = {"doc"}
    display_name = "doc"

    def extract(self, path: Path, rel_path: str, cfg) -> Document:
        method = cfg.get("extractors", "doc", {}).get("method", "auto")
        text = ""
        if method in ("auto", "antiword"):
            antiword = shutil.which("antiword")
            if antiword:
                text = self._via_antiword(antiword, path)
        if not text and method in ("auto", "libreoffice"):
            soffice = shutil.which("soffice") or shutil.which("libreoffice")
            if soffice:
                text = self._via_libreoffice(soffice, path)
        if not text:
            raise ExtractorError(
                "解析 .doc 需要系统工具：antiword 或 LibreOffice。"
                "请安装其一（Windows 可安装 LibreOffice 并确保 soffice 在 PATH 中），"
                "或在 extractors.doc.method 指定解析方式。"
            )
        return self.make_doc(path, rel_path, "doc", text,
                             meta={"lines": text.count("\n") + 1, "method": method})

    @staticmethod
    def _via_antiword(antiword: str, path: Path) -> str:
        try:
            proc = subprocess.run([antiword, str(path)], capture_output=True, timeout=120)
            if proc.returncode == 0:
                return proc.stdout.decode("utf-8", errors="replace")
        except Exception:
            pass
        return ""

    @staticmethod
    def _via_libreoffice(soffice: str, path: Path) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            try:
                proc = subprocess.run(
                    [soffice, "--headless", "--convert-to", "txt:Text", "--outdir", tmp, str(path)],
                    capture_output=True, timeout=300,
                )
                if proc.returncode != 0:
                    return ""
                out = Path(tmp) / (path.stem + ".txt")
                if out.exists():
                    return out.read_text(encoding="utf-8", errors="replace")
            except Exception:
                pass
        return ""
