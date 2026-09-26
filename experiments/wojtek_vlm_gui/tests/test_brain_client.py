"""The page's ROS 2 client against a mock node. No ROS runtime.

What it guards: the page writes only the instruction and the cancel (never
/cmd_vel, never a goal), reads only the brain's and goto's status and the
annotated picture (never a camera topic), refuses a task nobody listens
to, and stops in the web console's order. Needs rclpy importable (the
wojtek_vlm_gui container); skipped elsewhere.
"""

import json
from unittest.mock import MagicMock

import numpy as np
import pytest

pytest.importorskip("rclpy")

from sensor_msgs.msg import Image  # noqa: E402
from std_msgs.msg import Empty, String  # noqa: E402

from wojtek_vlm_gui import limits  # noqa: E402
from wojtek_vlm_gui.brain_client import BrainClient  # noqa: E402


def _client(listening=True):
    """A mock node that hands out one publisher mock per topic, so the
    order and the target of every publish can be checked."""
    node = MagicMock()
    pubs = {}
    node.create_publisher.side_effect = lambda _t, topic, _d: pubs.setdefault(topic, MagicMock())
    node.count_subscribers.return_value = 1 if listening else 0
    return BrainClient(node, subscriber_wait_s=0.05, poll_s=0.01), node, pubs


def test_the_only_publishers_are_the_instruction_and_the_cancel():
    _, node, _ = _client()
    created = {c.args[1]: c.args[0] for c in node.create_publisher.call_args_list}
    assert created == {limits.INSTRUCTION_TOPIC: String, limits.CANCEL_TOPIC: Empty}
    for topic in limits.NEVER_PUBLISHED:
        assert topic not in created


def test_the_subscriptions_are_the_status_topics_and_the_annotated_picture_only():
    _, node, _ = _client()
    topics = {c.args[1] for c in node.create_subscription.call_args_list}
    assert topics == {limits.VLM_STATUS_TOPIC, limits.GOTO_STATUS_TOPIC,
                      limits.PIXEL_STATUS_TOPIC, limits.ANNOTATED_TOPIC}
    assert not any("camera" in t for t in topics)


def test_send_publishes_the_instruction_as_typed():
    client, _, pubs = _client()
    ok, msg = client.send("  go to the purple pillar ")
    assert ok and "go to the purple pillar" in msg
    assert pubs[limits.INSTRUCTION_TOPIC].publish.call_args.args[0].data == "go to the purple pillar"
    pubs[limits.CANCEL_TOPIC].publish.assert_not_called()


def test_send_refuses_when_no_brain_listens_and_publishes_nothing():
    client, _, pubs = _client(listening=False)
    ok, msg = client.send("go to the purple pillar")
    assert not ok
    assert limits.INSTRUCTION_TOPIC in msg and "vlm:=true" in msg
    pubs[limits.INSTRUCTION_TOPIC].publish.assert_not_called()


def test_stop_sends_the_cancel_first_then_the_empty_instruction():
    order = []
    client, _, pubs = _client()
    pubs[limits.CANCEL_TOPIC].publish.side_effect = lambda m: order.append(("cancel", m))
    pubs[limits.INSTRUCTION_TOPIC].publish.side_effect = lambda m: order.append(("instruction", m.data))

    ok, _ = client.stop()

    assert ok
    assert [o[0] for o in order] == ["cancel", "instruction"]
    assert order[1][1] == ""


def test_a_stop_word_typed_as_a_task_is_a_stop_even_with_no_brain():
    client, _, pubs = _client(listening=False)
    ok, msg = client.send("stop")
    assert ok and msg == "STOP sent"
    pubs[limits.CANCEL_TOPIC].publish.assert_called_once()
    assert pubs[limits.INSTRUCTION_TOPIC].publish.call_args.args[0].data == ""


def test_status_messages_land_in_the_log_in_order_and_per_task():
    client, _, _ = _client()

    def status(**kw):
        client._on_status(String(data=json.dumps(kw)))

    status(action="ask", step=1, instruction="go to the pillar", t=1.0, answer={"type": "not_visible"})
    status(action="turn", step=1, instruction="go to the pillar", t=1.5, deg=45.0, turned_total=45.0)
    status(action="finished", step=2, instruction="go to the pillar", t=2.0, result="cancelled")
    status(action="ask", step=1, instruction="go to the box", t=3.0, answer={"type": "goal"})
    client._on_status(String(data="garbage"))  # ignored, never raises

    snap = client.latest()
    assert snap["instruction"] == "go to the box"
    assert [s["action"] for s in snap["lines"]] == ["ask"]
    assert snap["finished"] is None and not snap["idle"]


def test_the_annotated_picture_is_pinned_to_the_next_ask():
    client, _, _ = _client()
    msg = Image()
    msg.encoding, msg.height, msg.width = "rgb8", 2, 3
    msg.data = bytes(range(2 * 3 * 3))
    client._on_annotated(msg)
    client._on_status(String(data=json.dumps({"action": "ask", "step": 1, "instruction": "x", "t": 0})))
    client._on_status(String(data=json.dumps({"action": "verify", "step": 1, "instruction": "x", "t": 0})))

    lines = client.latest()["lines"]
    img = lines[0]["_image"]
    assert isinstance(img, np.ndarray) and img.shape == (2, 3, 3) and img[1, 2, 2] == 17
    assert "_image" not in lines[1]


def test_a_picture_in_another_encoding_is_ignored():
    client, _, _ = _client()
    msg = Image()
    msg.encoding, msg.height, msg.width = "bgr8", 1, 1
    msg.data = bytes(3)
    client._on_annotated(msg)
    assert client._annotated is None


def test_nav_status_words_are_kept_latest():
    client, _, _ = _client()
    client._on_goto(String(data="driving"))
    client._on_pixel(String(data="sent"))
    client._on_goto(String(data="reached"))
    snap = client.latest()
    assert (snap["goto"], snap["pixel"]) == ("reached", "sent")
