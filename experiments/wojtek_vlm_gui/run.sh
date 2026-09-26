#!/usr/bin/env bash
# Entry point for the Wojtek VLM GUI experiment. Self-contained on purpose:
# nothing outside this directory is configured to know about it. See README.md.
#
# Everything runs in the wojtek_vlm_gui container (docker/compose.yaml), a
# sibling of wojtek_robot on the same host network and DDS domain. Start the
# simulation first, from the repository root:
#   ./ros/sim.sh model_xml:=scene_nav.xml leg_odom:=true nav:=true vlm:=true
set -euo pipefail
cd "$(dirname "$0")"
HERE="$PWD"
CONTAINER=wojtek_vlm_gui

usage() {
  cat >&2 <<'USAGE'
usage: run.sh {build|up|down|shell|gui|test} [args]
  build    build the wojtek_vlm_gui image (once per machine)
  up       start the container (idempotent)
  down     stop and remove it
  shell    interactive shell inside it (ROS 2 sourced, venv on PATH)
  gui      the operator page: streamlit on http://localhost:8501
  test     model-free unit tests (EXP_PY=<host python> to run outside docker)
USAGE
}

compose() {
  (cd "$HERE/docker" && docker compose "$@")
}

up() {
  compose up -d wojtek_vlm_gui
}

# Runs a command inside the container through the image entrypoint, which
# sources ROS 2 and cds into /exp.
cexec() {
  docker exec -i "$CONTAINER" /entrypoint.sh "$@"
}

case "${1:-}" in
  build)
    shift
    compose build "$@"
    ;;
  up)
    up
    ;;
  down)
    compose down
    ;;
  shell)
    up
    exec docker exec -it "$CONTAINER" /entrypoint.sh bash
    ;;
  gui)
    shift
    up
    # -i only (no -t): works from a plain terminal and from a background job.
    exec docker exec -i "$CONTAINER" /entrypoint.sh \
      streamlit run --server.headless=true --server.showEmailPrompt=false \
      --server.port=8501 wojtek_vlm_gui/app.py "$@"
    ;;
  test)
    shift
    if [ -n "${EXP_PY:-}" ]; then
      exec "$EXP_PY" -m pytest tests -q "$@"
    fi
    up
    # The venv sees the system site-packages, where ros-dev-tools' apt
    # pytest plugins (launch_testing) may be built against an older pytest
    # and break entry-point autoload; load only the plugin this suite needs.
    cexec env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -p pytest_timeout tests -q "$@"
    ;;
  *)
    usage
    exit 1
    ;;
esac
