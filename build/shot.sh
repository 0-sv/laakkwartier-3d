#!/bin/sh
# usage: shot.sh out.png [hash] [width,height]
DIR=$(cd "$(dirname "$0")/.." && pwd)
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --disable-extensions \
  --user-data-dir="${TMPDIR:-/tmp}/laak-chrome" --window-size="${3:-1440,900}" \
  --virtual-time-budget=12000 --screenshot="$1" "file://$DIR/index.html#$2" 2>/dev/null
