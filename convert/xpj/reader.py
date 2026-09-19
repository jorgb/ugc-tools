"""
Reads an MPC XPJ project back into its header lines and JSON structure - the
inverse of writer.serialize(). Used to inspect and diff real MPC projects
against converter output. See convert/xpj/DESIGN.md section 4.1.
"""

import gzip
import json

_GZIP_MAGIC = b"\x1f\x8b"
_XML_MAGIC = b"<?xml"
_HEADER_MAGIC = "ACVS"


def parse(raw_bytes):
    """Decodes XPJ bytes into (header_lines, project_data).

    header_lines is every line before the JSON body (the writer emits 5), so
    an unexpected header on a real project shows up instead of being dropped.
    """
    if raw_bytes.startswith(_XML_MAGIC):
        raise ValueError("XML project (MPC 2.x format) - only the gzip+JSON 3.x format is supported")

    if raw_bytes.startswith(_GZIP_MAGIC):
        raw_bytes = gzip.decompress(raw_bytes)

    if not raw_bytes.startswith(_HEADER_MAGIC.encode("ascii")):
        raise ValueError(f"Not an XPJ file: expected {_HEADER_MAGIC!r} header, got {raw_bytes[:16]!r}")

    lines = raw_bytes.decode("utf-8").split("\n")
    body_start = next((i for i, line in enumerate(lines) if line.lstrip().startswith("{")), None)
    if body_start is None:
        raise ValueError("XPJ file has a header but no JSON body")

    header_lines = lines[:body_start]
    project_data = json.loads("\n".join(lines[body_start:]))
    return header_lines, project_data


def read_project(xpj_path):
    """Reads an .xpj file, returns (header_lines, project_data)."""
    with open(xpj_path, 'rb') as f:
        return parse(f.read())


def to_json_text(project_data):
    """Pretty-prints project_data, keeping the file's own key order so two
    dumps diff cleanly."""
    return json.dumps(project_data, indent=2, ensure_ascii=False) + "\n"
