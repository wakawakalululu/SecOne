#!/usr/bin/env bash
# SecOne Linux/macOS 打包：PyInstaller onedir → 可移植 tar.gz + SHA256。
# 与 Windows 的 Nuitka 产物同等布局：程序旁边放 config/、assets/、licenses/、
# models/（仅清单与候选列表）、runtime/（仅 README），模型权重与推理引擎
# 不入包。产物不带签名，macOS 首次运行需 `xattr -cr <目录>` 去除隔离属性。
#
# 用法：build_unix.sh [--skip-tests]   （PYTHON 环境变量可指定解释器）
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-python3}"
SKIP_TESTS=0
for arg in "$@"; do
  case "$arg" in
    --skip-tests) SKIP_TESTS=1 ;;
    *) echo "未知参数: $arg" >&2; exit 2 ;;
  esac
done

cd "$ROOT"
echo "Python: $PYTHON"
"$PYTHON" -c "import sys; print(sys.version)"

if [[ $SKIP_TESTS -ne 1 ]]; then
  echo "运行测试 ..."
  "$PYTHON" -m pytest tests -q
fi

if ! "$PYTHON" -c "import PyInstaller" >/dev/null 2>&1; then
  "$PYTHON" -m pip install pyinstaller
fi

VERSION="$("$PYTHON" -c "import yaml; print(yaml.safe_load(open('config/app.yaml', encoding='utf-8'))['app']['version'])")"
OS="$(uname -s | tr '[:upper:]' '[:lower:]')"
case "$OS" in
  darwin) SYS="macos" ;;
  linux) SYS="linux" ;;
  *) echo "不支持的平台: $OS" >&2; exit 2 ;;
esac
ARCH="$(uname -m)"

BUILD="$ROOT/build/pyinstaller"
DIST="$ROOT/dist"
TARGET="$DIST/SecOne"
rm -rf "$BUILD" "$TARGET"
mkdir -p "$BUILD" "$DIST"

echo "PyInstaller onedir 构建 ..."
PYTHONPATH="$ROOT/src" "$PYTHON" -m PyInstaller \
  --noconfirm --clean \
  --name SecOne \
  --paths "$ROOT/src" \
  --collect-submodules secone \
  --distpath "$BUILD" \
  --workpath "$BUILD/_work" \
  --specpath "$BUILD" \
  run_secone.py

cp -R "$BUILD/SecOne" "$TARGET"
cp -R "$ROOT/config" "$TARGET/config"
cp -R "$ROOT/assets" "$TARGET/assets"
cp -R "$ROOT/licenses" "$TARGET/licenses"
mkdir -p "$TARGET/models" "$TARGET/runtime" "$TARGET/data" "$TARGET/workspace" "$TARGET/output" "$TARGET/logs"
cp "$ROOT/models/model.json" "$ROOT/models/candidates.json" "$ROOT/models/README.md" "$TARGET/models/"
cp "$ROOT/runtime/README.md" "$TARGET/runtime/"
cp "$ROOT/LICENSE" "$ROOT/NOTICE.md" "$ROOT/THIRD_PARTY_NOTICES.md" "$TARGET/"

PKG="SecOne-${VERSION}-portable-${SYS}-${ARCH}"
TARBALL="$DIST/${PKG}.tar.gz"
tar -C "$DIST" -czf "$TARBALL" "$(basename "$TARGET")"
( cd "$DIST" && shasum -a 256 "$(basename "$TARBALL")" > "$(basename "$TARBALL").sha256" )

echo
echo "构建完成：$TARBALL"
