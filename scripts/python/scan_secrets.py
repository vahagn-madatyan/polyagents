#!/usr/bin/env python3
"""
Lightweight secret scanner for pre-commit.

This scans staged text files for common credential patterns and fails the commit
if any likely secret is detected.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


KEY_NAMES = (
    "OPENAI_API_KEY",
    "NEWSAPI_API_KEY",
    "TAVILY_API_KEY",
    "ALCHEMY_API_KEY",
    "CLOB_API_KEY",
    "CLOB_SECRET",
    "CLOB_PASS_PHRASE",
    "POLYGON_WALLET_PRIVATE_KEY",
    "PRIVATE_KEY",
)

ASSIGNMENT_RE = re.compile(
    r"(?P<name>\b(?:"
    + "|".join(KEY_NAMES)
    + r")\b)\s*[:=]\s*(?P<value>\"[^\"]*\"|'[^']*'|[^\s#]+)"
)

RAW_TOKEN_PATTERNS = (
    ("openai_key", re.compile(r"sk-(?:proj-)?[A-Za-z0-9_-]{20,}")),
    ("github_pat", re.compile(r"ghp_[A-Za-z0-9]{20,}")),
    ("aws_access_key", re.compile(r"(?:AKIA|ASIA)[0-9A-Z]{16}")),
    ("slack_token", re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}")),
    (
        "jwt",
        re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    ),
    (
        "private_key_pem",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    ),
)

HEX_PRIVATE_KEY_RE = re.compile(r"0x[a-fA-F0-9]{64}")
HEX_PRIVATE_CONTEXT_RE = re.compile(
    r"(?i)(private[_ -]?key|seed|mnemonic|wallet[_ -]?key|secret)"
)


def _normalize_value(raw_value: str) -> str:
    value = raw_value.strip()
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        value = value[1:-1].strip()
    return value


def _is_placeholder(value: str) -> bool:
    if not value:
        return True

    lowered = value.strip().lower()
    if lowered in {
        "...",
        "***",
        "<api_key>",
        "api_key",
        "your_api_key",
        "changeme",
        "change_me",
        "placeholder",
        "redacted",
        "none",
        "null",
    }:
        return True

    if "<" in value and ">" in value:
        return True
    if lowered.startswith("${") and lowered.endswith("}"):
        return True
    if lowered.startswith("$"):
        return True
    if "os.environ/" in lowered or "process.env." in lowered:
        return True
    if "example" in lowered:
        return True
    if lowered.startswith("https://") and (
        "<api_key>" in lowered or "your_api_key" in lowered
    ):
        return True

    return False


def _is_probably_text(path: Path) -> bool:
    try:
        data = path.read_bytes()
    except OSError:
        return False
    return b"\x00" not in data


def _scan_file(path: Path) -> list[str]:
    findings: list[str] = []
    if not path.exists() or not path.is_file():
        return findings
    if not _is_probably_text(path):
        return findings

    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return findings

    for lineno, line in enumerate(content.splitlines(), start=1):
        if "pragma: allowlist secret" in line.lower():
            continue

        assignment = ASSIGNMENT_RE.search(line)
        if assignment:
            name = assignment.group("name")
            value = _normalize_value(assignment.group("value"))
            if not _is_placeholder(value):
                findings.append(
                    f"{path}:{lineno}: hardcoded value for {name} looks like a secret"
                )

        for label, pattern in RAW_TOKEN_PATTERNS:
            if pattern.search(line):
                findings.append(f"{path}:{lineno}: potential secret detected ({label})")

        if HEX_PRIVATE_KEY_RE.search(line) and HEX_PRIVATE_CONTEXT_RE.search(line):
            findings.append(
                f"{path}:{lineno}: potential EVM private key literal detected in key context"
            )

    return findings


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Scan files for likely committed secrets."
    )
    parser.add_argument("files", nargs="*", help="Files passed by pre-commit.")
    args = parser.parse_args(argv)

    findings: list[str] = []
    for file_name in args.files:
        findings.extend(_scan_file(Path(file_name)))

    if findings:
        print("Secret scan failed. Resolve findings before commit:\n")
        for finding in findings:
            print(f" - {finding}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
