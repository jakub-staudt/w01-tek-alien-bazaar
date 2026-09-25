#!/usr/bin/env bash
# perf.sh -- profile the robot computer from the PC, one scenario at a time.
#
# Brings up the robot's own launch (the arguments of its wojtek-robot
# service, read from the RPi) with the motors mocked (mock_hw:=true) and
# telemetry on, adds the scenario's extras, runs probe.py on the RPi and
# saves its JSON under results/. The boot service is stopped while a
# perf stack runs and started again by `down`.
#
#   ./ros/hw_tests/perf/perf.sh sync                 # copy probe to the RPi
#   ./ros/hw_tests/perf/perf.sh run <scenario> [secs] [extra launch args...]
#   ./ros/hw_tests/perf/perf.sh up <scenario> [extra launch args...]
#   ./ros/hw_tests/perf/perf.sh probe <label> [secs] [--viewer] [--camera]
#   ./ros/hw_tests/perf/perf.sh down                 # restore the boot service
#   ./ros/hw_tests/perf/perf.sh logs                 # tail the perf stack's log
#   ./ros/hw_tests/perf/perf.sh scenarios            # list them
#
# Nothing here arms the robot: real_io_node comes up DISARMED as always,
# and with mock_hw:=true there are no drives to arm. MOCK=0 runs the real
# drivers instead (motors powered, human present -- see ros/README.md).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
# shellcheck disable=SC1091
[ -f "$REPO/.env" ] && set -a && . "$REPO/.env" && set +a
RPI_HOST="${RPI_HOST:-rpi@10.42.0.2}"
RPI_ADDR="${RPI_HOST#*@}"
REMOTE_DIR="${REMOTE_DIR:-wojtek_perf}"     # relative to the RPi user's home
UNIT="wojtek-perf-stack"
MOCK="${MOCK:-1}"
RESULTS="$HERE/results"

ssh_rpi() { ssh -o BatchMode=yes -o ConnectTimeout=5 "$RPI_HOST" "$@"; }

# Scenario -> launch arguments added on top of the service's own.
scenario_args() {
  case "$1" in
    stack)  echo "" ;;                                    # control stack only
    deck)   echo "deck:=true" ;;                          # + panel gateway
    camera) echo "deck:=true deck_camera:=true deck_camera_depth:=false" ;;  # + colour only
    vlm)    echo "deck:=true deck_camera:=true deck_camera_depth:=true" ;;   # + depth for the VLM
    full)   echo "deck:=true deck_camera:=true deck_camera_depth:=true foxglove:=true" ;;
    *) echo "unknown scenario '$1' (see: perf.sh scenarios)" >&2; return 1 ;;
  esac
}

usage() { sed -n '2,22p' "$0" | sed 's/^# \{0,1\}//'; }

cmd_scenarios() {
  cat <<'EOF'
stack   control stack only (ros2_control, real_io, policy, pad teleop)
deck    + deck_gateway (panel, websocket), no camera
camera  + RealSense colour stream (compressed transport) feeding the gateway
vlm     camera + depth from the same node (probe times colour JPEG and depth)
full    vlm + foxglove_bridge (connect Foxglove to ws://<robot>:8765)
Add a viewer to any of them with `probe ... --viewer` (the PC pulls the
MJPEG stream while the probe measures); `run` does it for camera/full.
EOF
}

cmd_sync() {
  ssh_rpi "mkdir -p ~/$REMOTE_DIR"
  rsync -a "$HERE/probe.py" "$RPI_HOST:$REMOTE_DIR/"
  echo "probe synced to $RPI_HOST:~/$REMOTE_DIR"
}

cmd_up() {
  local scenario="${1:?scenario}"; shift
  local extra; extra="$(scenario_args "$scenario")"
  local mock="mock_hw:=true"
  [ "$MOCK" = "0" ] && mock=""
  # The service's own launch arguments, so the perf stack is the robot's
  # stack and not a copy that drifts from it.
  # ssh joins its arguments into one remote command line, hence the %q.
  local overrides; overrides="$(echo $mock telemetry:=true $extra "$@")"
  ssh_rpi "bash -s -- $UNIT $(printf %q "$overrides")" <<'REMOTE'
set -euo pipefail
unit="$1"; overrides="$2"
exec_line="$(systemctl cat wojtek-robot.service | grep '^ExecStart=.\+' | tail -1)"
base_args="$(sed -n "s/.*robot\.launch\.py\([^']*\)'.*/\1/p" <<<"$exec_line")"
if [ -z "$base_args" ]; then
  echo "could not read the service's launch arguments" >&2; exit 1
fi
# An override replaces the service's value for the same key.
for kv in $overrides; do
  base_args="$(sed -E "s/(^| )${kv%%:=*}:=[^ ]*//g" <<<"$base_args")"
done
env_py="$(systemctl show wojtek-robot.service -p Environment --value)"
# Remember whether the boot service was running, for `down`.
if systemctl is-active -q wojtek-robot.service; then
  touch "/tmp/$unit.restore"
  sudo systemctl stop wojtek-robot.service
fi
sudo systemctl stop "$unit" 2>/dev/null || true
sudo systemctl reset-failed "$unit" 2>/dev/null || true
env_args=()
for kv in $env_py; do env_args+=(-E "$kv"); done
sudo systemd-run --unit="$unit" --uid=rpi --gid=rpi \
  -p LimitRTPRIO=99 -p LimitMEMLOCK=infinity "${env_args[@]}" \
  /usr/bin/taskset -c 2,3 /bin/bash -lc "source /opt/ros/jazzy/setup.bash && source /home/rpi/wojtek_ws/install/setup.bash && exec ros2 launch wojtek_bringup robot.launch.py $base_args $overrides" >/dev/null
echo "started $unit:$base_args $overrides"
REMOTE
}

cmd_down() {
  ssh_rpi bash -s -- "$UNIT" <<'REMOTE'
unit="$1"
sudo systemctl stop "$unit" 2>/dev/null || true
sudo systemctl reset-failed "$unit" 2>/dev/null || true
if [ -f "/tmp/$unit.restore" ]; then
  rm -f "/tmp/$unit.restore"
  sudo systemctl start wojtek-robot.service
  echo "perf stack stopped; wojtek-robot.service started again"
else
  echo "perf stack stopped (wojtek-robot.service was not running before)"
fi
REMOTE
}

cmd_logs() { ssh_rpi "journalctl -u $UNIT -n ${1:-80} --no-pager -o cat"; }

cmd_probe() {
  local label="${1:?label}"; shift
  local secs=30
  if [ $# -gt 0 ] && [[ "$1" =~ ^[0-9]+$ ]]; then secs="$1"; shift; fi
  local viewer=0 probe_flags=""
  for a in "$@"; do
    case "$a" in
      --viewer) viewer=1 ;;
      --camera) probe_flags="$probe_flags --camera" ;;
      --topic) want_topic=1; continue ;;
      *)
        if [ "${want_topic:-0}" = 1 ]; then
          probe_flags="$probe_flags --topic $a"; want_topic=0
        else
          echo "unknown probe flag $a" >&2; return 1
        fi ;;
    esac
  done
  mkdir -p "$RESULTS"
  local stamp; stamp="$(date +%Y%m%d-%H%M%S)"
  local out="$RESULTS/$stamp-$label.json"
  local viewer_out; viewer_out="$(mktemp)"
  local vpid=""
  if [ "$viewer" = 1 ]; then
    # The gateway comes up with the stack: wait for its port, then start the
    # viewer just before the window (the probe settles 5 s first) so the
    # camera is already streaming when measuring starts.
    local deadline=$((SECONDS + 120))
    until curl -s -o /dev/null -m 2 "http://$RPI_ADDR:8090/"; do
      if [ $SECONDS -ge $deadline ]; then echo "gateway never came up" >&2; break; fi
      sleep 2
    done
    python3 "$HERE/viewer.py" "http://$RPI_ADDR:8090/stream.mjpg" \
      --duration "$((secs + 8))" >"$viewer_out" &
    vpid=$!
  fi
  local since; since="$(ssh_rpi date +%s)"
  ssh_rpi "source /opt/ros/jazzy/setup.bash && source ~/wojtek_ws/install/setup.bash && \
    export ROS_DOMAIN_ID=42 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp CYCLONEDDS_URI=file:///etc/cyclonedds-rpi.xml && \
    taskset -c 0 nice -n 5 python3 ~/$REMOTE_DIR/probe.py --duration $secs --label $label $probe_flags" >"$out.tmp"
  # Controller overruns and warnings the stack logged during the window.
  local overruns warns
  overruns="$(ssh_rpi "journalctl -u $UNIT --since @$since -o cat --no-pager | grep -ci \"overrun detected\"" || true)"
  warns="$(ssh_rpi "journalctl -u $UNIT --since @$since -o cat --no-pager | grep -E 'WARN|ERROR' | sed 's/\[[0-9.]*\]//' | sort | uniq -c | sort -rn | head -8" || true)"
  if [ -n "$vpid" ]; then wait "$vpid" || true; fi
  python3 - "$out.tmp" "$out" "$viewer_out" "$overruns" "$warns" <<'PY'
import json, sys
src, dst, viewer_path, overruns, warns = sys.argv[1:6]
report = json.load(open(src))
try:
    report["viewer"] = json.load(open(viewer_path))
except (OSError, ValueError):
    pass
report["log"] = {"overrun_lines": int(overruns or 0),
                 "warnings": [w.strip() for w in warns.splitlines() if w.strip()]}
json.dump(report, open(dst, "w"), indent=1)
PY
  rm -f "$out.tmp" "$viewer_out"
  python3 "$HERE/compare.py" "$out"
  echo "saved $out"
}

cmd_run() {
  local scenario="${1:?scenario}"; shift
  local secs=30
  if [ $# -gt 0 ] && [[ "$1" =~ ^[0-9]+$ ]]; then secs="$1"; shift; fi
  cmd_sync >/dev/null
  cmd_up "$scenario" "$@"
  case "$scenario" in
    camera) cmd_probe "$scenario" "$secs" --viewer ;;
    vlm|full) cmd_probe "$scenario" "$secs" --viewer \
           --topic "/camera/camera/depth/image_rect_raw=sensor_msgs/msg/Image" ;;
    *) cmd_probe "$scenario" "$secs" ;;
  esac
}

case "${1:-}" in
  sync) shift; cmd_sync "$@" ;;
  up) shift; cmd_up "$@" ;;
  down) shift; cmd_down "$@" ;;
  probe) shift; cmd_probe "$@" ;;
  run) shift; cmd_run "$@" ;;
  logs) shift; cmd_logs "$@" ;;
  scenarios) cmd_scenarios ;;
  *) usage; exit 1 ;;
esac
