# wojtek_spectacles_bridge

Status: **verified working against the MuJoCo simulator (2026-09-26).
Not yet run against the real robot.**

Bridges the Snap Spectacles pinch-drag joystick (`Snap_Spectacles/Assets/PinchDragNavigator.ts`)
to `/cmd_vel`. A plain WebSocket server (`ws://<host>:<port>/ws`, default
port 8766 in the sim) receives `{"vx", "wz"}` JSON at ~10 Hz from the Lens
and republishes the same `/cmd_vel` surface the gamepad, web console, and
`text_commander` use.

Dead-man contract matches `wojtek_teleop/text_commander.py`: exactly one
zero `Twist` on timeout (`command_timeout` parameter, default 0.5s), then
silence -- so it never fights another drive source once the connection is
gone.

Started only by hand, inside the sim container:

```bash
ros2 run wojtek_spectacles_bridge spectacles_bridge --ros-args -p port:=8766
```

`_run_bridge.sh` in this directory wraps the command above plus the
`AMENT_PREFIX_PATH` workaround described in
[`ros/docs/spectacles-lens-setup.md`](../../docs/spectacles-lens-setup.md) --
`ros2 run` cannot find this package straight after `colcon build` on this
workspace without it.

Not added to any launch file and not a dependency of `wojtek_bringup` -- it
does not affect the robot's normal autonomous startup.

## Before promoting out of experimental status

- Run it against the real robot with someone spotting/e-stop ready.
- Confirm `vx_limit` / `wz_limit` defaults (0.3 m/s, 0.5 rad/s) match what's
  safe for the current gait/policy.
- Decide whether it needs to become a permanent `ros/src/` package with a
  launch-file entry (per this repo's isolation rule, nothing here may become
  a dependency of `wojtek_bringup` or reach the robot through
  `ros/deploy.sh` while it stays an experiment).
