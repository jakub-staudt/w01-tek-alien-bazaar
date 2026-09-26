"""The walker's dead reckoning and guide. Pure."""

import math

import pytest

from wojtek_vlm_gui.walker import Walker


def run(w, seconds, dt=0.05, t0=0.0, refresh=None):
    """Step the walker; `refresh` re-sends a command each tick like goto/the brain."""
    t = t0
    for _ in range(int(round(seconds / dt))):
        t += dt
        if refresh:
            w.command(*refresh, now=t)
        w.step(t, dt)
    return t


def test_a_brain_turn_of_45_deg_turns_the_mock_45_deg():
    # the brain: 0.5 rad/s for radians(45)/0.38 s
    w = Walker()
    run(w, math.radians(45) / 0.38, refresh=(0.0, 0.0, 0.5))
    assert math.degrees(w.yaw) == pytest.approx(45.0, abs=1.5)
    assert w.segment_deg == pytest.approx(45.0, abs=1.5)
    assert (w.x, w.y) == (0.0, 0.0)


def test_walking_forward_moves_along_the_heading():
    w = Walker()
    w.yaw = math.pi / 2          # facing +y
    run(w, 2.0, refresh=(0.3, 0.0, 0.0))
    assert w.x == pytest.approx(0.0, abs=1e-9) and w.y == pytest.approx(0.6, abs=0.02)
    assert w.segment_m == pytest.approx(0.6, abs=0.02)


def test_a_command_goes_stale_after_the_dead_man():
    w = Walker()
    w.command(0.3, 0.0, 0.0, now=0.0)
    run(w, 2.0)                  # never refreshed
    assert w.x == pytest.approx(0.3 * 0.5, abs=0.02)   # moved only until 0.5 s
    assert w.guide(2.0)["kind"] == "still" and w.instruction(2.0) == "STAND STILL"


def test_instructions_name_what_to_do():
    w = Walker()
    w.command(0.0, 0.0, -0.5, now=0.0)
    g = w.guide(0.1)
    assert g["kind"] == "turn" and g["heading_deg"] == -90.0
    assert g["text"].startswith("TURN RIGHT on the spot")
    w.command(0.3, 0.0, 0.2, now=1.0)
    g = w.guide(1.1)
    assert g["kind"] == "walk" and "WALK FORWARD 0.30 m/s" in g["text"] and "curving left" in g["text"]


def test_a_new_segment_restarts_its_counter():
    w = Walker()
    t = run(w, 1.0, refresh=(0.0, 0.0, 0.5))
    assert w.segment_deg > 0
    run(w, 1.0, t0=t, refresh=(0.3, 0.0, 0.0))
    assert w.segment_deg == 0.0 and w.segment_m == pytest.approx(0.3, abs=0.02)


def test_goal_vector_is_relative_to_the_robot():
    w = Walker()
    w.set_goal_odom(1.0, 1.0)
    v = w.goal_vector()
    assert v["dist_m"] == pytest.approx(1.41, abs=0.01) and v["bearing_deg"] == pytest.approx(45.0)
    w.yaw = math.pi / 2          # now facing +y: the goal is 45 deg to the right
    assert w.goal_vector()["bearing_deg"] == pytest.approx(-45.0)


def test_a_goal_in_base_link_is_anchored_in_odom_at_the_current_pose():
    w = Walker()
    w.x, w.y, w.yaw = 1.0, 0.0, math.pi / 2
    w.set_goal_base(2.0, 0.0)    # 2 m straight ahead
    assert w.goal == pytest.approx((1.0, 2.0))
    w.clear_goal()
    assert w.guide(0.0)["goal"] is None
