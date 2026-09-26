"""The operator page for a VLM session: Streamlit, port 8501.

    ./experiments/wojtek_vlm_gui/run.sh gui      ->  http://localhost:8501

An instruction typed here goes to wojtek_nav's vlm_brain_node, which does
every inference and motion decision (ros/src/wojtek_nav/README.md); the
page shows the brain's step log and the picture it answered on, and keeps
the operator's Robot buttons. It composes no prompt, calls no model,
publishes no /cmd_vel and reads no camera stream.
"""

from __future__ import annotations

import streamlit as st

from wojtek_vlm_gui.arm_switch import lie_down, set_armed, set_policy_enabled, stand_up
from wojtek_vlm_gui.brain_client import start_client
from wojtek_vlm_gui.task_log import format_line, verdict

REFRESH_S = 0.5
OPERATOR_RULE = ("STOP the brain before driving with the pad or the Deck: a running task "
                 "and a stick share /cmd_vel. Disarm also stops the brain.")

st.set_page_config(page_title="Wojtek VLM", page_icon=":dog:", layout="wide")


@st.cache_resource
def get_client():
    return start_client()


# -- the Robot panel: the operator's buttons, the same gates the pad and the
# Deck flip. real_io: stand_up / lie_down ramp slowly (refused while armed);
# arm lets the policy's targets reach the motors (refused unless standing in
# the home pose). policy_node: enable/disable the RL gait. Disarm and Lie
# down also STOP the brain: disarming stops the motors, not a task that
# would otherwise keep publishing goals into a disarmed robot.


def _robot_button(col, label: str, call, key: str, kind: str = "secondary", stops_brain: bool = False) -> None:
    if col.button(label, key=key, type=kind, use_container_width=True):
        client = get_client()
        ok, msg = call(client.node)
        if stops_brain:
            client.stop()
            msg = f"{msg} (brain STOP sent)"
        st.session_state["robot_msg"] = ("ok" if ok else "err", f"{label}: {msg}")
        if label == "Arm" and ok:
            st.session_state["armed"] = True
        if label == "Disarm" and ok:
            st.session_state["armed"] = False


def _robot_panel() -> None:
    st.subheader("Robot")
    c1, c2 = st.columns(2)
    _robot_button(c1, "Stand up", stand_up, "btn_stand")
    _robot_button(c2, "Lie down", lie_down, "btn_lie", stops_brain=True)
    _robot_button(c1, "Arm", lambda n: set_armed(n, True), "btn_arm", "primary")
    _robot_button(c2, "Disarm", lambda n: set_armed(n, False), "btn_disarm", "primary", stops_brain=True)
    _robot_button(c1, "Policy on", lambda n: set_policy_enabled(n, True), "btn_pol_on")
    _robot_button(c2, "Policy off", lambda n: set_policy_enabled(n, False), "btn_pol_off")
    kind, msg = st.session_state.get("robot_msg", ("ok", ""))
    if msg:
        (st.success if kind == "ok" else st.error)(msg)
    if st.session_state.get("armed", False):
        st.warning("ARMED: a task moves the robot. Hand on power.")
    st.caption("Order: Stand up -> Arm -> type a task. Disarm before Lie down.")


@st.fragment(run_every=REFRESH_S)
def _nav_panel() -> None:
    """goto's and the resolver's latched status words."""
    snap = get_client().latest()
    st.subheader("Navigation")
    st.code(f"goto:  {snap['goto'] or '-'}\npixel: {snap['pixel'] or '-'}", language=None)


@st.fragment(run_every=REFRESH_S)
def _brain_panel() -> None:
    """The task in flight: one line per brain status, the annotated picture
    under each `ask`, the result word at the end. Re-rendered on its own
    timer so the page follows the brain without a manual refresh."""
    snap = get_client().latest()
    if not snap["lines"]:
        st.info("brain: no status yet (is the session up with vlm:=true?)")
        return
    st.markdown(f"**task:** {snap['instruction'] or '(none)'}")
    for line in snap["lines"]:
        st.code(format_line(line), language=None)
        img = line.get("_image")
        if img is not None:
            st.image(img, caption=f"step {line.get('step')}: the picture the brain answered on",
                     use_container_width=True)
    fin = snap["finished"]
    if fin is not None:
        text = f"finished: {fin.get('result')}" + (f" -- {fin['error']}" if fin.get("error") else "")
        (st.success if verdict(fin) == "ok" else st.error)(text)


def main() -> None:
    st.title("Wojtek VLM")
    client = get_client()
    with st.sidebar:
        _robot_panel()
        _nav_panel()

    c_in, c_stop = st.columns([6, 1])
    with c_stop:
        if st.button("STOP", type="primary", use_container_width=True):
            ok, msg = client.stop()
            st.session_state["send_msg"] = ("ok" if ok else "err", msg)
    with c_in:
        st.caption(OPERATOR_RULE)
    kind, msg = st.session_state.get("send_msg", ("ok", ""))
    if msg:
        (st.info if kind == "ok" else st.error)(msg)

    _brain_panel()

    prompt = st.chat_input("Tell Wojtek where to go, e.g. go to the purple pillar")
    if prompt:
        ok, msg = client.send(prompt)
        st.session_state["send_msg"] = ("ok" if ok else "err", msg)
        st.rerun()


if __name__ == "__main__":
    main()
