"""The page's ROS 2 side: a thin client of wojtek_nav's vlm_brain_node.

Publishes the operator's instruction on wojtek/vlm/instruction and the
cancel on wojtek/nav/cancel; subscribes to the brain's status JSON, the
two nav status words and the annotated picture. Nothing else: no /cmd_vel
(the drive sources' topic), no camera topic (the brain reads the camera,
the page shows only the frame the brain annotated, one per model call).

`BrainClient` takes any node-like object (the tests hand it a mock);
`start_client` makes the real node and spins it on a daemon thread so
Streamlit's own thread never blocks on ROS.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, Optional, Tuple

import numpy as np
import rclpy
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import Image
from std_msgs.msg import Empty, String

from wojtek_vlm_gui import limits
from wojtek_vlm_gui.task_log import TaskLog, is_stop_word, parse_status

# The brain and goto publish their status latched (depth 1, reliable,
# transient local); a subscriber with the same profile gets the last one
# on connect instead of waiting for the next step.
LATCHED = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                     durability=DurabilityPolicy.TRANSIENT_LOCAL)
ANNOTATED_ENCODING = "rgb8"


class BrainClient:
    def __init__(self, node, subscriber_wait_s: float = limits.SUBSCRIBER_WAIT_S,
                 poll_s: float = limits.SUBSCRIBER_POLL_S) -> None:
        self.node = node
        self._wait_s = float(subscriber_wait_s)
        self._poll_s = float(poll_s)
        self._lock = threading.Lock()
        self.log = TaskLog()
        self.goto_status: Optional[str] = None
        self.pixel_status: Optional[str] = None
        self._annotated: Optional[np.ndarray] = None
        self._pub_instruction = node.create_publisher(String, limits.INSTRUCTION_TOPIC, 10)
        self._pub_cancel = node.create_publisher(Empty, limits.CANCEL_TOPIC, 10)
        node.create_subscription(String, limits.VLM_STATUS_TOPIC, self._on_status, LATCHED)
        node.create_subscription(String, limits.GOTO_STATUS_TOPIC, self._on_goto, LATCHED)
        node.create_subscription(String, limits.PIXEL_STATUS_TOPIC, self._on_pixel, LATCHED)
        node.create_subscription(Image, limits.ANNOTATED_TOPIC, self._on_annotated, 1)

    # -- out -------------------------------------------------------------

    def send(self, text: str) -> Tuple[bool, str]:
        """Publish a task. A stop word is a stop. Refuses, with a message,
        when no brain subscribes within the wait: never a silent no-op."""
        text = text.strip()
        if is_stop_word(text):
            return self.stop()
        if not self._brain_listening():
            return False, (f"no brain is listening on {limits.INSTRUCTION_TOPIC} "
                           "(is the session up with vlm:=true?)")
        self._pub_instruction.publish(String(data=text))
        return True, f"sent: {text}"

    def stop(self) -> Tuple[bool, str]:
        """The web console's order: the cancel first (goto and the resolver
        drop their goal even with no brain running), then the empty
        instruction (the brain halts and reports `cancelled`)."""
        self._pub_cancel.publish(Empty())
        self._pub_instruction.publish(String(data=""))
        return True, "STOP sent"

    def _brain_listening(self) -> bool:
        deadline = time.monotonic() + self._wait_s
        while True:
            if self.node.count_subscribers(limits.INSTRUCTION_TOPIC) > 0:
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(self._poll_s)

    # -- in --------------------------------------------------------------

    def _on_status(self, msg) -> None:
        status = parse_status(msg.data)
        if status is None:
            return
        with self._lock:
            # The brain publishes the annotated picture right before the
            # `ask` status of the same step; pin it to that line.
            if status.get("action") == "ask" and self._annotated is not None:
                status["_image"] = self._annotated
            self.log.push(status)

    def _on_goto(self, msg) -> None:
        with self._lock:
            self.goto_status = msg.data

    def _on_pixel(self, msg) -> None:
        with self._lock:
            self.pixel_status = msg.data

    def _on_annotated(self, msg) -> None:
        if msg.encoding != ANNOTATED_ENCODING:
            return
        img = np.frombuffer(bytes(msg.data), dtype=np.uint8).reshape(msg.height, msg.width, 3)
        with self._lock:
            self._annotated = img

    def latest(self) -> Dict[str, Any]:
        """A snapshot for one render: the task's lines, the nav words."""
        with self._lock:
            return {
                "instruction": self.log.instruction,
                "lines": list(self.log.lines),
                "finished": self.log.finished,
                "idle": self.log.idle,
                "goto": self.goto_status,
                "pixel": self.pixel_status,
            }


def start_client(node_name: str = "wojtek_vlm_gui") -> BrainClient:
    """The real node, spun on a daemon thread. Streamlit calls `send`,
    `stop` and `latest` from its own thread; rclpy allows publishing from
    any thread, and the callbacks land under the client's lock."""
    if not rclpy.ok():
        rclpy.init()
    node = Node(node_name)
    client = BrainClient(node)
    executor = SingleThreadedExecutor()
    executor.add_node(node)
    threading.Thread(target=executor.spin, name="wojtek_vlm_gui_spin", daemon=True).start()
    return client
