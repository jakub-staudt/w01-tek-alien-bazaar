# Wojtek x Spectacles

Snap Spectacles (gen 5) Lens Studio project for controlling Wojtek. Built in
Lens Studio 5.15.4 with the Spectacles Interaction Kit (SIK).

## Status

Working pinch-and-drag virtual joystick: pinch with a hand, drag to set
direction/speed, an on-screen glass-locked arrow shows the command, release
to stop. Self-contained (no robot networking yet) — this validates the AR
interaction on-device before wiring it to ROS.

`Assets/PinchDragNavigator.ts` computes `currentVx` / `currentWz` from the
drag; nothing consumes them yet.

## Opening the project

Open `Alien Bazaar - spectacles.esproj` in Lens Studio 5.15.4+. The
Spectacles Interaction Kit package under `Packages/` is required for hand
tracking.

## Not yet built

- Networking the joystick output to the robot (planned: a
  `wojtek_spectacles_bridge` ROS 2 node under `experiments/` in this repo,
  receiving commands over WebSocket and publishing `/cmd_vel`).
- Tap-to-select-object navigation (planned: a tapped pixel goes to
  `wojtek_nav`'s pixel resolver on `/wojtek/nav/pixel_goal`, which turns it
  into a setpoint for `goto`).
