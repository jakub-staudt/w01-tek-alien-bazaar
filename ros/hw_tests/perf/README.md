# Robot computer profiling (`perf.sh`)

Measures what the RPi does while running Wojtek's stack: control-loop and
policy rates and their worst gaps, policy inference time, per-core and
per-thread CPU, interrupts on the isolated cores, temperature and
throttling, and the camera stream as a viewer on the PC receives it.
Every run is one JSON file under `results/` (gitignored), so a change can
be measured before and after with the same command.

The stack under test is the robot's own: `perf.sh up` reads the launch
arguments of the RPi's `wojtek-robot.service` and starts the same launch
as a transient unit, with two additions: `mock_hw:=true` (the MD80 drives
and the IMU replaced by ros2_control's GenericSystem, so the motors can
stay unpowered) and `telemetry:=true` (for `/wojtek/policy_timing`). The
boot service is stopped while a perf stack runs and started again by
`down` if it had been running. Nothing arms the robot.

What the mock leaves out: the CANdle's SPI traffic and the blocking I2C
IMU read. Numbers measured with it are the floor of the real load. `MOCK=0`
runs the real drivers (motors powered, a person at the robot).

## Use

From the repository root, with the RPi reachable (`RPI_HOST`, default
`rpi@10.42.0.2`, over the cable):

```bash
./ros/hw_tests/perf/perf.sh run stack 30      # control stack only, 30 s window
./ros/hw_tests/perf/perf.sh run camera 30     # + colour camera + panel, PC as the viewer
./ros/hw_tests/perf/perf.sh down              # stop it, restore the boot service

# Finer steps: bring a scenario up once, probe it several times.
./ros/hw_tests/perf/perf.sh up camera deck_camera_profile:=424x240x15
./ros/hw_tests/perf/perf.sh probe small-camera 30 --viewer
./ros/hw_tests/perf/perf.sh logs

# Before / after.
python3 ros/hw_tests/perf/compare.py results/A.json results/B.json
```

Extra arguments to `up`/`run` are launch arguments and override the
service's own (`deck_stream_hz:=10`, `policy_cpus:=1`, ...).

A changed package reaches the RPi with `ros/deploy.sh` (or, while
iterating on one package, an rsync of it into `~/wojtek_ws/src` plus
`colcon build --packages-select <pkg>` there; Python and launch files are
symlink-installed and need no rebuild).

## Files

| File | Runs on | Does |
|---|---|---|
| `perf.sh` | PC | scenarios, the transient unit, collecting results |
| `probe.py` | RPi | one measurement window -> JSON (subscribes only, pinned to core 0) |
| `viewer.py` | PC | pulls the panel's MJPEG stream like the Deck would, times it |
| `compare.py` | PC | the summary table, one or several results side by side |
