"""
Extract cookies from Chrome/Edge via CDP, then write Netscape cookies.txt for yt-dlp.

Bypasses two Windows problems:
1. Chrome/Edge lock the SQLite cookie database while running
2. Chrome v130+ uses App-Bound Encryption (requires admin to decrypt via file)

CDP extraction works because the browser itself decrypts cookies in memory.

Usage:
    python cdp_extract_cookies.py [--browser chrome|edge] [--domains douyin.com,bilibili.com] [--output cookies.txt]

Requirements: pip install websocket-client

If Chrome/Edge was NOT launched with --remote-debugging-port, this script can
temporarily launch a browser instance with that flag to extract cookies (--launch).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def find_browser_path(browser: str) -> str | None:
    candidates = {
        "chrome": [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ],
        "edge": [
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        ],
    }
    for p in candidates.get(browser, []):
        if Path(p).exists():
            return p
    return None


def get_profile_dir(browser: str) -> str:
    local_app = os.environ.get("LOCALAPPDATA", "")
    dirs = {
        "chrome": Path(local_app) / "Google" / "Chrome" / "User Data",
        "edge": Path(local_app) / "Microsoft" / "Edge" / "User Data",
    }
    return str(dirs.get(browser, ""))


def find_existing_debug_port(profile_dir: str) -> int | None:
    port_file = Path(profile_dir) / "DevToolsActivePort"
    if not port_file.exists():
        return None
    try:
        return int(port_file.read_text().strip().splitlines()[0].strip())
    except Exception:
        return None


def launch_browser_with_debug(browser_path: str, port: int, profile_dir: str) -> subprocess.Popen | None:
    try:
        return subprocess.Popen(
            [
                browser_path,
                f"--remote-debugging-port={port}",
                "--remote-allow-origins=*",
                f"--user-data-dir={profile_dir}",
                "--no-first-run",
                "--no-default-browser-check",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return None


def get_ws_url(port: int, timeout: float = 10) -> str | None:
    import urllib.request
    for endpoint in [f"http://127.0.0.1:{port}/json/version", f"http://127.0.0.1:{port}/json"]:
        try:
            resp = urllib.request.urlopen(endpoint, timeout=timeout)
            data = json.loads(resp.read())
            if isinstance(data, dict):
                return data.get("webSocketDebuggerUrl")
            if isinstance(data, list):
                for t in data:
                    if t.get("type") == "page":
                        return t.get("webSocketDebuggerUrl")
        except Exception:
            continue
    return None


def cdp_get_all_cookies(port: int, domains: list[str] | None = None) -> list[dict]:
    import websocket as ws_mod

    ws_url = get_ws_url(port)
    if not ws_url:
        raise RuntimeError(f"No CDP WebSocket at port {port}")

    ws = ws_mod.create_connection(ws_url, timeout=15)
    try:
        ws.send(json.dumps({"id": 1, "method": "Network.getAllCookies"}))
        while True:
            resp = json.loads(ws.recv())
            if resp.get("id") == 1:
                cookies = resp.get("result", {}).get("cookies", [])
                break
    finally:
        ws.close()

    if domains:
        cookies = [c for c in cookies if any(c.get("domain", "").endswith(d) for d in domains)]
    return cookies


def cookies_to_netscape(cookies: list[dict]) -> str:
    lines = ["# Netscape HTTP Cookie File", ""]
    for c in sorted(cookies, key=lambda x: (x.get("domain", ""), x.get("path", ""), x.get("name", ""))):
        domain = c.get("domain", "")
        flag = "TRUE" if domain.startswith(".") else "FALSE"
        path = c.get("path", "/")
        secure = "TRUE" if c.get("secure", False) else "FALSE"
        expires = int(c.get("expires", -1))
        if expires < 0:
            expires = 0
        name = c.get("name", "")
        value = c.get("value", "")
        lines.append(f"{domain}\t{flag}\t{path}\t{secure}\t{expires}\t{name}\t{value}")
    return "\n".join(lines) + "\n"


def ensure_websocket_client() -> None:
    try:
        import websocket  # noqa: F401
    except ImportError:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "websocket-client"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )


def try_extract_from_browser(browser: str, domains: list[str] | None, launch: bool) -> list[dict] | None:
    """Try to extract cookies from a single browser. Returns cookies or None."""
    profile_dir = get_profile_dir(browser)
    if not profile_dir or not Path(profile_dir).exists():
        return None

    port = find_existing_debug_port(profile_dir)
    launched_proc = None

    if not port:
        if not launch:
            return None
        browser_path = find_browser_path(browser)
        if not browser_path:
            return None
        port = 9222
        launched_proc = launch_browser_with_debug(browser_path, port, profile_dir)
        if not launched_proc:
            return None
        print(f"Launched {browser} on port {port}, waiting for page load...", file=sys.stderr)
        time.sleep(5)

    try:
        cookies = cdp_get_all_cookies(port, domains)
        return cookies
    except Exception as exc:
        print(f"CDP extraction from {browser} failed: {exc}", file=sys.stderr)
        return None
    finally:
        if launched_proc:
            launched_proc.terminate()


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract cookies from Chrome/Edge via CDP for yt-dlp")
    parser.add_argument("--browser", choices=["chrome", "edge", "auto"], default="auto",
                        help="Browser to extract from (auto: try Chrome then Edge)")
    parser.add_argument("--domains", default="douyin.com,bilibili.com",
                        help="Comma-separated domain suffixes")
    parser.add_argument("--output", "-o", help="Output cookies.txt path (default: stdout)")
    parser.add_argument("--port", type=int, default=0, help="Use existing CDP port (0 = auto-detect)")
    parser.add_argument("--launch", action="store_true",
                        help="Launch browser with debug port if not already running")
    args = parser.parse_args()

    domain_list = [d.strip() for d in args.domains.split(",") if d.strip()] if args.domains else None

    ensure_websocket_client()

    cookies: list[dict] | None = None

    if args.port:
        # Use specified port directly
        try:
            cookies = cdp_get_all_cookies(args.port, domain_list)
        except Exception as exc:
            print(f"CDP extraction on port {args.port} failed: {exc}", file=sys.stderr)
            return 1
    elif args.browser == "auto":
        # Try Chrome first, then Edge
        for browser in ["chrome", "edge"]:
            result = try_extract_from_browser(browser, domain_list, args.launch)
            if result is not None and len(result) > 0:
                cookies = result
                print(f"Extracted {len(cookies)} cookies from {browser}", file=sys.stderr)
                break
            if result is not None and len(result) == 0:
                print(f"No matching cookies in {browser}", file=sys.stderr)
    else:
        cookies = try_extract_from_browser(args.browser, domain_list, args.launch)

    if not cookies:
        print("ERROR: Could not extract cookies from any browser", file=sys.stderr)
        return 1

    netscape_text = cookies_to_netscape(cookies)

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(netscape_text, encoding="utf-8")
        print(f"Wrote {len(cookies)} cookies to {args.output}", file=sys.stderr)
    else:
        print(netscape_text)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
