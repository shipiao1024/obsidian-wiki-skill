#!/usr/bin/env python3
"""obsidian-wiki-skill 依赖检查与安装脚本。

用法：
  python scripts/check_deps.py              # 仅检查，不安装
  python scripts/check_deps.py --install    # 检查 + 自动安装缺失依赖
  python scripts/check_deps.py --install --china  # 使用中国镜像安装
  python scripts/check_deps.py --install --group=wechat  # 仅安装微信组依赖
  python scripts/check_deps.py --install-camoufox       # 仅安装 Camoufox 浏览器
  python scripts/check_deps.py --install-camoufox --china # 用 ghfast.top 镜像安装

中国无 VPN 环境的关键经验（试错总结）：
  - GitHub 直连下载 ~300KB/s，530MB 需要 30+ 分钟
  - ghproxy.com / mirror.ghproxy.com → 超时不可用
  - ghfast.top → 可用，8.5MB/s，60 秒下载 530MB
  - addons.mozilla.org → 返回 HTTP 451（中国屏蔽）
  - UBO addon 需从 GitHub 通过 ghfast.top 下载
  - Camoufox 启动时会检查 addons，如果缺失会清空 Cache 重新下载
    所以必须先安装 UBO addon，否则手动解压的浏览器会被删除
"""
from __future__ import annotations

import importlib
import io
import json
import os
import shutil
import subprocess
import sys
import zipfile

# ── Prevent camoufox from auto-downloading and destroying Cache ──────────────
# camoufox.pkgman.camoufox_path() calls CamoufoxFetcher().install() when the
# browser binary is missing. That call FIRST cleans Cache, THEN tries to
# download from GitHub — which fails in China, leaving Cache empty.
# We monkey-patch it to raise immediately instead of nuking the installation.
try:
    import camoufox.pkgman as _cpm

    _original_camoufox_path = _cpm.camoufox_path

    def _safe_camoufox_path(download_if_missing: bool = True):
        if not os.path.exists(_cpm.INSTALL_DIR) or not os.listdir(_cpm.INSTALL_DIR):
            raise FileNotFoundError(
                f"Camoufox binary not found at {_cpm.INSTALL_DIR}. "
                "Run: python scripts/check_deps.py --install-camoufox --china"
            )
        return _original_camoufox_path(download_if_missing=False)

    _cpm.camoufox_path = _safe_camoufox_path
except ImportError:
    pass
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
TOOLS_DIR = SKILL_DIR / ".tools"
WECHAT_TOOL_DIR = TOOLS_DIR / "wechat-article-for-ai"
DEPS_DIR = SKILL_DIR / ".python-packages"

CHINA_PIP_MIRROR = "https://pypi.tuna.tsinghua.edu.cn/simple"
CHINA_NPM_MIRROR = "https://registry.npmmirror.com"

# GitHub 镜像列表，按实测可用性排序
GH_MIRRORS = [
    "https://ghfast.top/",      # 可用, 8.5MB/s (2026-04 测)
    "https://gh-proxy.com/",     # 待验证
    "https://github.moeyy.xyz/", # 待验证
    "https://hub.gitmirror.com/",# 待验证
    "https://ghproxy.com/",      # 2026-04 测超时
    "https://mirror.ghproxy.com/",# 2026-04 测超时
]

DEPS = {
    "python": {
        "label": "Python 3.11+",
        "kind": "system",
        "group": "core",
        "check": lambda: sys.version_info >= (3, 11),
        "fix_hint": "安装 Python 3.11+: https://www.python.org/downloads/",
    },
    "git": {
        "label": "Git",
        "kind": "system",
        "group": "core",
        "check": lambda: shutil.which("git") is not None,
        "fix_hint": "安装 Git: https://git-scm.com/download/win",
    },
    "wechat-tool": {
        "label": "wechat-article-for-ai",
        "kind": "git_clone",
        "group": "wechat",
        "path": WECHAT_TOOL_DIR,
        "check": lambda: WECHAT_TOOL_DIR.exists() and (WECHAT_TOOL_DIR / "main.py").exists(),
        "install_std": [
            "git", "clone", "--depth", "1",
            "https://github.com/bzd6661/wechat-article-for-ai.git",
            str(WECHAT_TOOL_DIR),
        ],
        "install_china": [
            "git", "clone", "--depth", "1",
            "https://ghfast.top/https://github.com/bzd6661/wechat-article-for-ai.git",
            str(WECHAT_TOOL_DIR),
        ],
        "fix_hint": "git clone https://github.com/bzd6661/wechat-article-for-ai.git .tools/wechat-article-for-ai\n中国镜像: 在 GitHub URL 前加 https://ghfast.top/",
    },
    "wechat-pip": {
        "label": "wechat-article-for-ai pip 依赖 (camoufox/markdownify/etc)",
        "kind": "pip_target",
        "group": "wechat",
        "check": lambda: _check_wechat_deps(),
        "install_std": ["pip", "install", "-r", str(WECHAT_TOOL_DIR / "requirements.txt"), "--target", str(DEPS_DIR)],
        "install_china": ["pip", "install", "-r", str(WECHAT_TOOL_DIR / "requirements.txt"), "--target", str(DEPS_DIR), "-i", CHINA_PIP_MIRROR],
        "fix_hint": "pip install -r .tools/wechat-article-for-ai/requirements.txt --target .python-packages\n中国镜像: 加 -i https://pypi.tuna.tsinghua.edu.cn/simple",
    },
    "chardet": {
        "label": "chardet (避免 requests 字符集告警)",
        "kind": "pip_target",
        "group": "wechat",
        "check": lambda: _try_import("chardet"),
        "install_std": ["pip", "install", "chardet", "--target", str(DEPS_DIR)],
        "install_china": ["pip", "install", "chardet", "--target", str(DEPS_DIR), "-i", CHINA_PIP_MIRROR],
        "fix_hint": "pip install chardet --target .python-packages",
    },
    "camoufox-browser": {
        "label": "Camoufox 浏览器 (~530MB 浏览器二进制 + UBO addon)",
        "kind": "camoufox_install",
        "group": "wechat",
        "check": lambda: _check_camoufox_complete(),
        "fix_hint": "python scripts/check_deps.py --install-camoufox\n中国镜像: python scripts/check_deps.py --install-camoufox --china",
    },
    "yt-dlp": {
        "label": "yt-dlp (视频字幕提取)",
        "kind": "pip",
        "group": "video",
        "check": lambda: shutil.which("yt-dlp") is not None or _try_import("yt_dlp"),
        "install_std": ["pip", "install", "-U", "yt-dlp"],
        "install_china": ["pip", "install", "-U", "yt-dlp", "-i", CHINA_PIP_MIRROR],
        "fix_hint": "pip install -U yt-dlp\n中国镜像: 加 -i https://pypi.tuna.tsinghua.edu.cn/simple",
    },
    "faster-whisper": {
        "label": "faster-whisper (视频 ASR fallback)",
        "kind": "pip",
        "group": "video_asr",
        "check": lambda: _try_import("faster_whisper"),
        "install_std": ["pip", "install", "faster-whisper"],
        "install_china": ["pip", "install", "faster-whisper", "-i", CHINA_PIP_MIRROR],
        "fix_hint": "pip install faster-whisper\n中国模型权重: set HF_ENDPOINT=https://hf-mirror.com",
    },
    "pypdf": {
        "label": "pypdf (本地 PDF 入库)",
        "kind": "pip",
        "group": "pdf",
        "check": lambda: _try_import("pypdf"),
        "install_std": ["pip", "install", "pypdf"],
        "install_china": ["pip", "install", "pypdf", "-i", CHINA_PIP_MIRROR],
        "fix_hint": "pip install pypdf\n中国镜像: 加 -i https://pypi.tuna.tsinghua.edu.cn/simple",
    },
    "baoyu-url-to-markdown": {
        "label": "baoyu-url-to-markdown (通用网页入库)",
        "kind": "custom",
        "group": "web",
        "check": lambda: _check_baoyu(),
        "fix_hint": "方式 1 (npm): npm install -g baoyu-url-to-markdown\n方式 2 (bun): 如果 baoyu-url-to-markdown skill 已安装, 设置环境变量:\n  set KWIKI_WEB_ADAPTER_BIN=bun <skill-path>/scripts/main.ts\n中国镜像 npm: 加 --registry=https://registry.npmmirror.com",
    },
    "nodejs": {
        "label": "Node.js (抖音浏览器捕获兜底)",
        "kind": "system",
        "group": "video",
        "check": lambda: shutil.which("node") is not None,
        "fix_hint": "安装 Node.js: https://nodejs.org/\n中国镜像: https://npmmirror.com/mirrors/node/",
    },
    "playwright": {
        "label": "Playwright Node 包 + Chromium (抖音浏览器捕获兜底)",
        "kind": "custom",
        "group": "video",
        "check": lambda: _check_playwright(),
        "fix_hint": "cd <skill-root>\nnpm install\nnpx playwright install chromium\n中国镜像: npm install --registry=https://registry.npmmirror.com\nnpx playwright install chromium",
    },
    "pytest": {
        "label": "pytest (测试套件)",
        "kind": "pip",
        "group": "test",
        "check": lambda: _try_import("pytest"),
        "install_std": ["pip", "install", "pytest>=8.0", "pytest-mock>=3.12"],
        "install_china": ["pip", "install", "pytest>=8.0", "pytest-mock>=3.12", "-i", CHINA_PIP_MIRROR],
        "fix_hint": "pip install pytest>=8.0 pytest-mock>=3.12",
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _try_import(name: str) -> bool:
    try:
        importlib.import_module(name)
        return True
    except ImportError:
        return False


def _check_baoyu() -> bool:
    """Check baoyu-url-to-markdown: either in PATH as npm global, or via bun."""
    if shutil.which("baoyu-url-to-markdown") is not None:
        return True
    # Check if baoyu skill exists and bun can run it
    baoyu_skill = Path.home() / ".claude" / "skills" / "baoyu-url-to-markdown" / "scripts" / "main.ts"
    if baoyu_skill.exists() and shutil.which("bun") is not None:
        return True
    return False


def _check_playwright() -> bool:
    """Check if Playwright npm package + Chromium browser are installed for douyin browser capture."""
    node_modules = SKILL_DIR / "node_modules" / "playwright"
    if not node_modules.exists():
        return False
    # Check if Chromium browser binary is installed
    try:
        result = subprocess.run(
            ["npx", "playwright", "install", "--dry-run", "chromium"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=str(SKILL_DIR), timeout=15,
        )
        return result.returncode == 0
    except Exception:
        # Fallback: just check node_modules exists
        return True


def _check_wechat_deps() -> bool:
    for pkg in ("camoufox", "markdownify", "beautifulsoup4", "httpx"):
        mod = {"beautifulsoup4": "bs4", "camoufox": "camoufox"}.get(pkg, pkg)
        if not _try_import(mod):
            return False
    return True


def _check_camoufox_complete() -> bool:
    """Check Camoufox browser binary + UBO addon + version.json all exist.
    Uses direct file checks to avoid triggering camoufox.pkgman's auto-download,
    which would wipe Cache on failure.
    """
    try:
        from camoufox.pkgman import INSTALL_DIR
    except ImportError:
        return False
    exe = INSTALL_DIR / "camoufox.exe"
    if not exe.exists():
        return False
    # Check version.json
    vj = INSTALL_DIR / "version.json"
    if not vj.exists():
        return False
    # Check UBO addon
    addons_dir = INSTALL_DIR / "addons" / "UBO"
    manifest = addons_dir / "manifest.json"
    if not manifest.exists():
        return False
    return True


def _find_working_mirror(url: str) -> str | None:
    """Try GitHub mirrors sequentially, return first that responds within timeout."""
    import httpx
    for mirror_prefix in GH_MIRRORS:
        mirror_url = mirror_prefix + url
        try:
            resp = httpx.head(mirror_url, follow_redirects=True, timeout=10)
            if resp.status_code in (200, 302, 301):
                return mirror_url
        except Exception:
            continue
    return None


# ---------------------------------------------------------------------------
# Camoufox install (the hard part)
# ---------------------------------------------------------------------------

def install_camoufox(use_china: bool = False) -> bool:
    """Install Camoufox browser binary + UBO addon.

    Standard path: python -m camoufox fetch (auto-downloads from GitHub)
    China path: download via ghfast.top mirror + manually extract + install UBO

    Trial-and-error notes (2026-04):
      - ghproxy.com / mirror.ghproxy.com → timeout (unusable)
      - ghfast.top → works, 8.5MB/s for 530MB file
      - addons.mozilla.org → HTTP 451 in China (blocked)
      - UBO XPI → download from GitHub via ghfast.top
      - Camoufox launch checks addons: if UBO missing → deletes Cache & re-downloads
        → must install UBO BEFORE using Camoufox, otherwise manual install wasted
    """
    if not use_china:
        # Standard: use camoufox's own fetch mechanism
        print("  [INSTALL] Camoufox (standard path: python -m camoufox fetch)")
        try:
            from camoufox.pkgman import CamoufoxFetcher
            f = CamoufoxFetcher()
            f.install()
            print("  [OK] Camoufox installed (standard)")
            return True
        except Exception as e:
            print(f"  [FAIL] Camoufox standard install: {e}")
            print("  提示: 如在中国无 VPN 环境，使用 --china 参数")
            return False

    # China: mirror download + manual install
    print("  [INSTALL] Camoufox (中国镜像路径: ghfast.top)")
    try:
        from camoufox.pkgman import INSTALL_DIR, CamoufoxFetcher
        import requests as req_lib
    except ImportError as e:
        print(f"  [FAIL] 缺少依赖: {e}")
        return False

    fetcher = CamoufoxFetcher()
    original_url = fetcher.url
    version_info = {"release": fetcher.release, "version": fetcher.version}

    # Step 1: Find working mirror
    print("  Step 1: 寻找可用 GitHub 镜像...")
    mirror_url = _find_working_mirror(original_url)
    if not mirror_url:
        # Fallback: try ghfast.top directly (known working)
        mirror_url = f"https://ghfast.top/{original_url}"
        print(f"  未找到可用镜像, 使用 ghfast.top: {mirror_url[:60]}...")
    else:
        print(f"  找到可用镜像: {mirror_url[:60]}...")

    # Step 2: Download browser zip
    print("  Step 2: 下载浏览器二进制 (~530MB)...")
    try:
        resp = req_lib.get(mirror_url, stream=True, timeout=(30, 600))
        if resp.status_code != 200:
            print(f"  [FAIL] HTTP {resp.status_code}")
            return False
        total = int(resp.headers.get("content-length", 0))
        print(f"  文件大小: {total / 1024 / 1024:.0f} MB")

        zip_path = Path.home() / "AppData" / "Local" / "camoufox" / "camoufox-china.zip"
        downloaded = 0
        with open(zip_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                f.write(chunk)
                downloaded += len(chunk)
                if downloaded % (50 * 1024 * 1024) < 65536:
                    pct = downloaded / total * 100 if total else 0
                    print(f"    {downloaded / 1024 / 1024:.0f}/{total / 1024 / 1024:.0f} MB ({pct:.1f}%)")
        print(f"  下载完成: {downloaded / 1024 / 1024:.0f} MB")
    except Exception as e:
        print(f"  [FAIL] 下载失败: {e}")
        return False

    # Step 3: Extract (clean old install first)
    print("  Step 3: 解压到安装目录...")
    if INSTALL_DIR.exists():
        shutil.rmtree(INSTALL_DIR, ignore_errors=True)
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            members = zf.namelist()
            for member in members:
                # Zip contains "camoufox/..." prefix
                target = INSTALL_DIR / member.removeprefix("camoufox/")
                if member.endswith("/"):
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member) as src, open(target, "wb") as dst:
                        dst.write(src.read())
    except zipfile.BadZipFile:
        print("  [FAIL] ZIP 文件损坏, 可能下载不完整")
        zip_path.unlink(missing_ok=True)
        return False
    print("  解压完成")

    # Step 4: Write version.json
    print("  Step 4: 写入 version.json...")
    with open(INSTALL_DIR / "version.json", "w") as f:
        json.dump(version_info, f)
    print(f"  version.json: {version_info}")

    # Step 5: Install UBO addon (critical — without this, Camoufox will delete Cache on launch)
    print("  Step 5: 安装 uBlock Origin addon...")
    ubo_result = _install_ubo_addon()
    if not ubo_result:
        print("  [WARN] UBO addon 安装失败, Camoufox 启动时可能重新下载整个浏览器")
        print("  提示: 如启动失败, 请手动安装 UBO 或使用 --exclude_addons=['UBO']")

    # Cleanup zip
    zip_path.unlink(missing_ok=True)

    # Step 6: Verify
    exe = INSTALL_DIR / "camoufox.exe"
    manifest = INSTALL_DIR / "addons" / "UBO" / "manifest.json"
    vj = INSTALL_DIR / "version.json"
    ok = exe.exists() and manifest.exists() and vj.exists()
    if ok:
        print("  [OK] Camoufox 完整安装成功 (浏览器 + UBO addon + version.json)")
    else:
        print(f"  [WARN] 安装不完整: exe={exe.exists()}, manifest={manifest.exists()}, vj={vj.exists()}")
    return ok


def _install_ubo_addon() -> bool:
    """Download and extract uBlock Origin addon for Camoufox.

    Trial-and-error (2026-04):
      - addons.mozilla.org → HTTP 451 in China (blocked)
      - ghfast.top + GitHub uBlock release → works
    """
    try:
        from camoufox.pkgman import INSTALL_DIR
    except ImportError:
        return False

    ubo_dir = INSTALL_DIR / "addons" / "UBO"
    if (ubo_dir / "manifest.json").exists():
        print("    UBO addon 已存在, 跳过")
        return True

    # Try Mozilla directly (works outside China)
    ubo_mozilla_url = "https://addons.mozilla.org/firefox/downloads/latest/ublock-origin/latest.xpi"

    # Try GitHub release (works via mirror)
    # Get latest release info
    import httpx
    api_url = "https://api.github.com/repos/gorhill/uBlock/releases/latest"
    gh_mirror_api = f"https://ghfast.top/{api_url}"

    xpi_data = None
    sources_tried = []

    # Attempt 1: Mozilla direct
    sources_tried.append("addons.mozilla.org (直连)")
    try:
        resp = httpx.get(ubo_mozilla_url, follow_redirects=True, timeout=15)
        if resp.status_code == 200 and len(resp.content) > 1000:
            xpi_data = resp.content
            print("    UBO: Mozilla 直连下载成功")
    except Exception:
        pass

    # Attempt 2: ghfast.top + GitHub API
    if xpi_data is None:
        sources_tried.append("ghfast.top + GitHub API")
        try:
            resp = httpx.get(gh_mirror_api, follow_redirects=True, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                for asset in data.get("assets", []):
                    if "firefox" in asset.get("name", "").lower() and "xpi" in asset.get("name", "").lower():
                        xpi_url = asset["browser_download_url"]
                        mirror_xpi_url = f"https://ghfast.top/{xpi_url}"
                        sources_tried.append(f"ghfast.top + GitHub XPI ({asset['name']})")
                        xpi_resp = httpx.get(mirror_xpi_url, follow_redirects=True, timeout=30)
                        if xpi_resp.status_code == 200 and len(xpi_resp.content) > 1000:
                            xpi_data = xpi_resp.content
                            print(f"    UBO: GitHub 镜像下载成功 ({asset['name']})")
                        break
        except Exception:
            pass

    # Attempt 3: direct GitHub (slow but may work)
    if xpi_data is None:
        sources_tried.append("GitHub 直连")
        try:
            resp = httpx.get(api_url, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                for asset in data.get("assets", []):
                    if "firefox" in asset.get("name", "").lower() and "xpi" in asset.get("name", "").lower():
                        xpi_url = asset["browser_download_url"]
                        xpi_resp = httpx.get(xpi_url, follow_redirects=True, timeout=30)
                        if xpi_resp.status_code == 200 and len(xpi_resp.content) > 1000:
                            xpi_data = xpi_resp.content
                            print(f"    UBO: GitHub 直连下载成功")
                        break
        except Exception:
            pass

    if xpi_data is None:
        print(f"    UBO: 所有来源均失败 (尝试了: {', '.join(sources_tried)})")
        return False

    # Extract XPI to addons/UBO
    ubo_dir.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(io.BytesIO(xpi_data)) as xpi:
            xpi.extractall(ubo_dir)
    except zipfile.BadZipFile:
        print("    UBO: XPI 文件损坏")
        return False

    manifest = ubo_dir / "manifest.json"
    ok = manifest.exists()
    if ok:
        count = len(list(ubo_dir.rglob("*")))
        print(f"    UBO: 安装成功 ({count} 文件)")
    else:
        print("    UBO: manifest.json 不存在, 安装可能损坏")
    return ok


# ---------------------------------------------------------------------------
# General install
# ---------------------------------------------------------------------------

def check_deps(groups: list[str] | None = None) -> list[tuple[str, str, bool]]:
    results = []
    for dep_id, dep in DEPS.items():
        if groups and dep["group"] not in groups:
            continue
        ok = dep["check"]()
        results.append((dep_id, dep["label"], ok))
    return results


def install_dep(dep_id: str, use_china: bool = False) -> bool:
    dep = DEPS[dep_id]

    if dep["kind"] == "camoufox_install":
        return install_camoufox(use_china)

    install_key = "install_china" if use_china else "install_std"
    cmd = dep.get(install_key)
    if not cmd:
        print(f"  [SKIP] {dep['label']} — 无自动安装命令 (kind={dep['kind']})")
        return False

    print(f"  [INSTALL] {dep['label']}...")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if result.returncode != 0:
            print(f"  [FAIL] {dep['label']}")
            stderr = result.stderr[:300] if result.stderr else ""
            if stderr:
                print(f"         {stderr}")
            return False
        print(f"  [OK] {dep['label']} 安装成功")
        return True
    except Exception as e:
        print(f"  [FAIL] {dep['label']}: {e}")
        return False


def main():
    args = sys.argv[1:]
    do_install = "--install" in args
    install_camoufox_only = "--install-camoufox" in args
    use_china = "--china" in args
    group_filter = None
    for a in args:
        if a.startswith("--group="):
            group_filter = a.split("=", 1)[1].split(",")

    # Special mode: install only Camoufox
    if install_camoufox_only:
        print("=" * 60)
        print("Camoufox 浏览器安装")
        print("=" * 60)
        if use_china:
            print("模式: 中国镜像 (ghfast.top)")
        else:
            print("模式: 标准 (GitHub 直连)")
        print()
        ok = install_camoufox(use_china)
        sys.exit(0 if ok else 1)

    print("=" * 60)
    print("obsidian-wiki-skill 依赖检查")
    print("=" * 60)
    if use_china:
        print(f"镜像模式: 中国 ({CHINA_PIP_MIRROR} + ghfast.top)")
    print()

    results = check_deps(group_filter)
    missing = []
    for dep_id, label, ok in results:
        status = "OK" if ok else "MISSING"
        icon = "OK" if ok else "!!"
        print(f"  [{icon}] {label}: {status}")
        if not ok:
            missing.append(dep_id)

    print()
    if not missing:
        print("所有依赖就绪!")
        return

    print(f"缺失 {len(missing)} 项依赖:")
    for dep_id in missing:
        dep = DEPS[dep_id]
        hint = dep.get("fix_hint", "")
        print(f"  - {dep['label']}")
        if hint:
            for line in hint.split("\n"):
                print(f"    {line}")

    if not do_install:
        print()
        print("运行以下命令自动安装缺失依赖:")
        cmd = "python scripts/check_deps.py --install"
        if use_china:
            cmd += " --china"
        if group_filter:
            cmd += f" --group={','.join(group_filter)}"
        print(f"  {cmd}")
        print()
        print("单独安装 Camoufox:")
        print("  python scripts/check_deps.py --install-camoufox")
        print("  python scripts/check_deps.py --install-camoufox --china  # 中国镜像")
        return

    print()
    print("开始自动安装...")
    DEPS_DIR.mkdir(parents=True, exist_ok=True)

    success = 0
    fail = 0
    for dep_id in missing:
        r = install_dep(dep_id, use_china)
        if r:
            success += 1
        else:
            fail += 1

    print()
    print(f"安装结果: {success} 成功, {fail} 失败")

    if fail > 0:
        print()
        print("部分安装失败。")
        if use_china:
            print("中国镜像失败时的备选方案:")
            print("  1. Camoufox: python scripts/check_deps.py --install-camoufox --china")
            print("  2. 设置代理: set HTTPS_PROXY=http://127.0.0.1:7890")
            print("  3. 手动下载: https://ghfast.top/https://github.com/daijro/camoufox/releases")
        else:
            print("  如在中国网络, 尝试: python scripts/check_deps.py --install --china")
        sys.exit(1)


if __name__ == "__main__":
    main()