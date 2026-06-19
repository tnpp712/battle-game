#!/usr/bin/env bash
# 从 assets/icon_1024.png 生成 macOS .icns 与 Windows .ico。
# 依赖：macOS 自带 sips/iconutil，Python 的 Pillow（pip install pillow）。
# 用法：先 `python3 tools/make_icon.py` 生成主图，再 `bash tools/build_icons.sh`。
set -euo pipefail
cd "$(dirname "$0")/.."

SRC=assets/icon_1024.png
[ -f "$SRC" ] || { echo "缺少 $SRC，请先运行 python3 tools/make_icon.py"; exit 1; }

# --- macOS .icns ---
ICONSET=$(mktemp -d)/icon.iconset
mkdir -p "$ICONSET"
for sz in 16 32 128 256 512; do
  sips -z $sz $sz "$SRC" --out "$ICONSET/icon_${sz}x${sz}.png" >/dev/null
  sips -z $((sz*2)) $((sz*2)) "$SRC" --out "$ICONSET/icon_${sz}x${sz}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o assets/icon.icns
echo "✅ assets/icon.icns"

# --- Windows .ico ---
python3 - <<'PY'
from PIL import Image
img = Image.open("assets/icon_1024.png").convert("RGBA")
img.save("assets/icon.ico", sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
print("✅ assets/icon.ico")
PY
