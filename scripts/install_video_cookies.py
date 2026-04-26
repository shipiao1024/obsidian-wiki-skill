from __future__ import annotations

import argparse
import sys
from pathlib import Path


def default_destination() -> Path:
    return Path(__file__).resolve().parents[1] / "cookies.txt"


def validate_netscape_cookie_text(text: str) -> None:
    normalized = text.lstrip("\ufeff").strip()
    if not normalized:
        raise ValueError("Cookie text is empty.")
    if not normalized.startswith("# Netscape HTTP Cookie File"):
        raise ValueError("Cookie text is not in Netscape cookies.txt format.")


def install_cookie_text(text: str, destination: Path | None = None) -> Path:
    validate_netscape_cookie_text(text)
    target = (destination or default_destination()).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = text.lstrip("\ufeff")
    if not payload.endswith("\n"):
        payload += "\n"
    target.write_text(payload, encoding="utf-8")
    return target


def install_cookie_file(source: Path, destination: Path | None = None) -> Path:
    text = source.read_text(encoding="utf-8")
    return install_cookie_text(text, destination=destination)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Install Bilibili/YouTube cookies.txt into the skill folder.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--source-file", type=Path, help="Path to an exported Netscape cookies.txt file.")
    group.add_argument("--stdin", action="store_true", help="Read Netscape cookies.txt content from stdin.")
    parser.add_argument("--destination", type=Path, help="Destination cookies.txt path. Defaults to skill-root cookies.txt.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.source_file:
            installed_path = install_cookie_file(args.source_file, destination=args.destination)
        else:
            installed_path = install_cookie_text(sys.stdin.read(), destination=args.destination)
    except FileNotFoundError as exc:
        raise SystemExit(f"Cookie source file not found: {exc.filename}") from exc
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    print(installed_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
