#!/bin/bash
set -euo pipefail

if [[ -z "${MANUAL_BROWSER_PASSWORD:-}" ]]; then
  echo "MANUAL_BROWSER_PASSWORD must be set" >&2
  exit 1
fi

password_file=/tmp/manual-browser.pass
x11vnc -storepasswd "$MANUAL_BROWSER_PASSWORD" "$password_file" >/dev/null
chmod 600 "$password_file"

pids=()
cleanup() {
  if ((${#pids[@]})); then
    kill "${pids[@]}" 2>/dev/null || true
    wait "${pids[@]}" 2>/dev/null || true
  fi
  rm -f "$password_file"
}
trap cleanup EXIT INT TERM

Xvfb :99 -screen 0 1440x900x24 -nolisten tcp &
pids+=("$!")
for _ in {1..50}; do
  [[ -S /tmp/.X11-unix/X99 ]] && break
  kill -0 "${pids[0]}" 2>/dev/null || exit 1
  sleep 0.1
done
if [[ ! -S /tmp/.X11-unix/X99 ]]; then
  echo "Xvfb did not become ready" >&2
  exit 1
fi
x11vnc -display :99 -rfbauth "$password_file" -forever -shared -localhost -noxdamage &
pids+=("$!")
websockify --web=/usr/share/novnc 6080 localhost:5900 &
pids+=("$!")
python -m app.manual_worker &
pids+=("$!")

# This service is one security boundary. If any part exits, stop the rest and
# let Compose restart the complete private browser stack.
wait -n "${pids[@]}"
