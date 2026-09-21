"""无损去掉 PNG 文本/EXIF，不解码像素、不重压 IDAT。"""

from __future__ import annotations

import binascii
import os
import shutil
from pathlib import Path

from app.util import ensure_dir, fs_path

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_DROP = {b"tEXt", b"zTXt", b"iTXt", b"eXIf", b"tIME"}


def is_png(path: Path) -> bool:
    try:
        with Path(path).open("rb") as handle:
            return handle.read(8) == PNG_MAGIC
    except OSError:
        return False


def _itxt_chunk(key: str, value: str) -> bytes:
    keyword = str(key or "litang").encode("latin-1", "replace")[:79]
    text = str(value or "").encode("utf-8")
    data = keyword + b"\x00\x00\x00\x00\x00" + text
    body = b"iTXt" + data
    crc = binascii.crc32(body) & 0xFFFFFFFF
    return len(data).to_bytes(4, "big") + body + crc.to_bytes(4, "big")


_MAX_CHUNK = 256 * 1024 * 1024


def _remove_file(path: Path) -> None:
    try:
        os.remove(fs_path(path))
    except OSError:
        pass


def _read_exact(src, length: int) -> bytes:
    if length > _MAX_CHUNK:
        raise ValueError("png chunk too large")
    buf = bytearray()
    while len(buf) < length:
        blob = src.read(min(1024 * 1024, length - len(buf)))
        if not blob:
            break
        buf.extend(blob)
    return bytes(buf)


def write_clean_png(source: Path, dest: Path, note: str = "") -> Path:
    source = Path(source)
    dest = Path(dest)
    ensure_dir(dest.parent)
    tmp = dest.with_name(dest.name + ".strip-tmp")
    if source.resolve() == dest.resolve():
        copied = dest.with_name(dest.name + ".src-tmp")
        shutil.copyfile(source, copied)
        source = copied
    else:
        copied = None
    try:
        with open(fs_path(source), "rb") as src, open(fs_path(tmp), "wb") as out:
            magic = src.read(8)
            if magic != PNG_MAGIC:
                raise ValueError("not a png")
            out.write(magic)
            while True:
                header = src.read(8)
                if len(header) < 8:
                    break
                length = int.from_bytes(header[:4], "big")
                ctype = header[4:8]
                data = _read_exact(src, length)
                crc = src.read(4)
                if len(data) < length or len(crc) < 4:
                    raise ValueError("truncated png")
                if ctype in _DROP:
                    continue
                if ctype == b"IEND":
                    if note:
                        out.write(_itxt_chunk("litang-baibaoxiang", note))
                    out.write(header)
                    out.write(data)
                    out.write(crc)
                    break
                out.write(header)
                out.write(data)
                out.write(crc)
        os.replace(fs_path(tmp), fs_path(dest))
        return dest
    finally:
        _remove_file(tmp)
        if copied is not None:
            _remove_file(copied)
