#!/usr/bin/env python3
"""Spectacles pinch-drag joystick -> /cmd_vel bridge.

Standalone package, started only by hand (`ros2 run`) -- not added to any
launch file or wojtek_bringup dependency, so the robot's normal autonomous
startup is completely unaffected by this existing in the workspace.

    ros2 run wojtek_spectacles_bridge spectacles_bridge
    ros2 run wojtek_spectacles_bridge spectacles_bridge --ros-args -p port:=8765

Runs a plain (non-TLS) WebSocket server. The Spectacles Lens
(Assets/PinchDragNavigator.ts in the Snap_Spectacles project) connects to
ws://<this-machine>:<port> over the "wojtek-net" hotspot and streams JSON
frames continuously at ~10 Hz:

    {"vx": <float m/s>, "wz": <float rad/s>}

...including {"vx": 0, "wz": 0} while the wearer isn't pinching -- that is
the heartbeat. This node republishes the SAME /cmd_vel surface the gamepad,
web console, and text_commander use, so nothing in wojtek_bringup /
wojtek_policy changes.

Dead-man, same contract as wojtek_teleop/text_commander.py: a command stays
active for `command_timeout` seconds after the last WebSocket frame: the
headset must keep talking to keep Wojtek walking. On timeout the node
publishes exactly ONE zero Twist and then goes silent -- the zero is
mandatory because policy_node latches the last received command forever,
and the silence lets another drive source (gamepad, web console) take
/cmd_vel without being fought. Since the Lens already sends a steady
heartbeat while connected, in practice the dead-man only fires on a real
WiFi drop, a crashed Lens, or the wearer taking the headset off.

vx/wz are also clamped here (`vx_limit`, `wz_limit` parameters) as a second,
robot-side backstop -- the Lens already clamps via its own
maxLinearSpeed/maxAngularSpeed inputs, but the authoritative limit belongs
on the robot, not the headset.

linear.z stays 0.0 = "use the default height" for policy_node, same as
text_commander and web_console.

Direction semantics match the joystick's drag mapping: vx is forward/back,
wz is turn left/right (yaw). There is no strafe (vy) -- Wojtek's gait is
driven as forward/back + turn, not omnidirectional.

Transport is aiohttp (already a dependency of wojtek_deck, already installed
on the robot -- no new pip install), the same web_console/deck_gateway
pattern: rclpy spins in a background thread, the websocket handler and the
drive tick both run on the asyncio thread, so no cross-thread marshaling is
needed for the state handoff (only ROS publishing crosses from asyncio into
rclpy, which Publisher.publish() allows from any thread).

Endpoint is ws://<host>:<port>/ws -- matches the `serverPath` input added to
PinchDragNavigator.ts alongside serverIp/serverPort.
"""
import asyncio
import json
import threading

import rclpy
from aiohttp import web
from geometry_msgs.msg import Twist
from rclpy.node import Node
from rclpy.signals import SignalHandlerOptions

DRIVE_TICK_HZ = 20.0     # /cmd_vel publish rate while active (same as consoles)


class SpectaclesCommandState:
    """Pure command core -- all behaviour, no rclpy (tested without ROS).

    `handle` arms/refreshes the current (vx, wz) on every WebSocket frame;
    `twist_to_publish` is the timer's question: (vx, wz) while fresh,
    exactly one (0, 0) on dead-man timeout, then None. Same shape as
    text_commander.CommandState, just fed continuous values instead of a
    fixed vocabulary of named commands.
    """

    def __init__(self, vx_limit, wz_limit, command_timeout):
        self._vx_limit = float(vx_limit)
        self._wz_limit = float(wz_limit)
        self._timeout = float(command_timeout)
        self._twist = None         # (vx, wz) while a command is fresh
        self._deadline = 0.0
        self._stop_sent = True     # nothing to zero out yet

    def handle(self, vx, wz, now):
        """Arm the latest (vx, wz), clamped to the robot-side limits."""
        vx = max(-self._vx_limit, min(self._vx_limit, float(vx)))
        wz = max(-self._wz_limit, min(self._wz_limit, float(wz)))
        self._twist = (vx, wz)
        self._deadline = now + self._timeout
        self._stop_sent = False

    def twist_to_publish(self, now):
        if self._twist is not None and now <= self._deadline:
            return self._twist
        self._twist = None          # timed out
        if self._stop_sent:
            return None
        self._stop_sent = True
        return (0.0, 0.0)


class SpectaclesBridgeNode(Node):
    def __init__(self):
        super().__init__("spectacles_bridge")
        vx_limit = self.declare_parameter("vx_limit", 0.3).value
        wz_limit = self.declare_parameter("wz_limit", 0.5).value
        timeout = self.declare_parameter("command_timeout", 0.5).value
        self.port = self.declare_parameter("port", 8765).value

        self.state = SpectaclesCommandState(vx_limit, wz_limit, timeout)
        self._pub_cmd = self.create_publisher(Twist, "cmd_vel", 10)

        self.get_logger().info(
            "spectacles bridge up -- "
            f"ws://0.0.0.0:{self.port}, vx<={vx_limit} m/s, "
            f"wz<={wz_limit} rad/s, dead-man {timeout} s"
        )

    def publish(self, twist):
        t = Twist()
        t.linear.x, t.angular.z = twist  # SpectaclesCommandState only emits floats
        # linear.z stays 0.0: policy_node reads that as "default height".
        self._pub_cmd.publish(t)


class Server:
    """Asyncio half: one WebSocket endpoint, no HTTP page."""

    def __init__(self, node: SpectaclesBridgeNode, loop):
        self.node = node
        self.loop = loop

    async def websocket(self, request):
        ws = web.WebSocketResponse(heartbeat=5.0)
        await ws.prepare(request)
        self.node.get_logger().info(f"Spectacles connected from {request.remote}")
        try:
            async for msg in ws:
                if msg.type != web.WSMsgType.TEXT:
                    continue
                try:
                    data = json.loads(msg.data)
                    vx = data["vx"]
                    wz = data["wz"]
                except (ValueError, KeyError, TypeError):
                    continue
                self.node.state.handle(vx, wz, self.loop.time())
        finally:
            self.node.get_logger().info("Spectacles disconnected")
        return ws

    async def drive_tick(self):
        while True:
            twist = self.node.state.twist_to_publish(self.loop.time())
            if twist is not None:
                self.node.publish(twist)
            await asyncio.sleep(1.0 / DRIVE_TICK_HZ)

    def app(self):
        app = web.Application()
        app.router.add_get("/ws", self.websocket)
        return app


def main():
    # No rclpy signal handlers: they would shut the ROS context down under
    # the spin thread and leave the server running with no ROS behind it.
    # The asyncio loop owns SIGINT/SIGTERM instead (same rule as deck_gateway).
    rclpy.init(signal_handler_options=SignalHandlerOptions.NO)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    node = SpectaclesBridgeNode()
    server = Server(node, loop)

    def spin():
        try:
            rclpy.spin(node)
        except Exception:  # noqa: BLE001 -- shutdown races raise here
            pass

    threading.Thread(target=spin, daemon=True).start()

    async def run():
        runner = web.AppRunner(server.app(), access_log=None)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", node.port)
        await site.start()
        node.get_logger().info(
            f"spectacles bridge listening on ws://0.0.0.0:{node.port}/ws")
        await server.drive_tick()

    try:
        loop.run_until_complete(run())
    except KeyboardInterrupt:
        pass
    finally:
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
