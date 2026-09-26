# Snap Spectacles -> Wojtek sim: host setup

Status: **verified working end-to-end (2026-09-26)** -- pinch-drag on the
physical Spectacles drives the Wojtek MuJoCo simulator, running entirely on
this Windows PC. The Spectacles never talk to the physical robot; the Lens
only ever points at this PC's LAN IP.

This doc is the "laptop got restarted, how do I get back to a working
state" reference. It covers the one-time host configuration and the
every-boot startup sequence separately.

## Architecture

```
Spectacles (Lens: PinchDragNavigator.ts)
   -- ws://<this PC's LAN IP>:8766/ws, JSON {"vx", "wz"} @ 10 Hz -->
Windows Firewall (inbound allow, TCP 8766)
   -->
netsh portproxy (0.0.0.0:8766 -> 127.0.0.1:8766)
   -->
WSL2 "Ubuntu" distro (mirrored networking mode)
   -->
Docker container "wojtek_robot"
   -->
ros2 node wojtek_spectacles_bridge (spectacles_bridge, --ros-args -p port:=8766)
   --> publishes /cmd_vel -->
ros2_control + MuJoCo hardware interface (the simulated robot)
```

Foxglove (`app.foxglove.dev` in a normal browser tab, logged in) connects
separately to `ws://localhost:8765` (the `foxglove_bridge` node, started by
`--foxglove`) to visualize the sim.

The Deck web dashboard (`deck_gateway` node) serves on `http://localhost:8090`.

## One-time host setup

Do these once per machine. They should survive reboots (they're persisted
Windows/WSL configuration), but if the Spectacles ever stop reaching the PC
again after a Windows update, re-check all three.

### 1. Docker Desktop + WSL2

Docker Desktop installed with the WSL2 backend, using the `Ubuntu` distro.
Install: `winget install --id Docker.DockerDesktop -e --source winget`.
Docker Desktop must be running (its tray icon) before anything below works.

### 2. WSL2 mirrored networking

`C:\Users\<you>\.wslconfig`:

```ini
[wsl2]
networkingMode=mirrored
```

This makes WSL2 share the Windows host's real network interface/IP instead
of sitting behind its own NAT, which is what makes a `netsh portproxy` rule
(next step) able to reach the container at all. Apply with:

```powershell
wsl --shutdown
```

(then restart Docker Desktop / any WSL terminal.)

### 3. Windows Firewall inbound rule

The bridge's port (8766) must be allowed inbound. In an **elevated**
PowerShell:

```powershell
New-NetFirewallRule -DisplayName "Wojtek Sim - Spectacles Bridge" -Direction Inbound -Protocol TCP -LocalPort 8766 -Action Allow -Profile Any
```

### 4. netsh portproxy rule

Even with mirrored networking, a service bound only inside WSL2/Docker
isn't reliably reachable from other LAN devices without an explicit
Windows-level forwarding rule. In the same **elevated** PowerShell:

```powershell
netsh interface portproxy add v4tov4 listenport=8766 listenaddress=0.0.0.0 connectport=8766 connectaddress=127.0.0.1
```

Verify any time with `netsh interface portproxy show all` -- should show
`0.0.0.0:8766 -> 127.0.0.1:8766`.

Note: curling this PC's own LAN IP (`curl http://<this-PC-LAN-IP>:8766/ws`)
*from this same PC* is expected to time out even when everything above is
correct -- Windows/WSL2 has a "hairpin NAT" limitation where a machine can't
always reach itself via its own external IP. That failure does **not** mean
the Spectacles (a genuinely separate device) can't reach it. The only
conclusive test is trying it from the headset.

### 5. Lens Studio project (already done, for reference)

In the Lens Studio project (`Snap_Spectacles/` in this repo):

- An **Internet Module** asset exists in the Asset Browser and is wired to
  `PinchDragNavigator`'s `internetModule` input. This is a hard requirement
  -- an unassigned Asset-typed input crashes the whole Lens on launch.
- **Project Settings -> Experimental APIs** is enabled (required for plain
  `ws://` to a local, non-TLS address).
- `PinchDragNavigator`'s inputs: `serverIp` = this PC's LAN IP (currently
  `192.168.8.131`), `serverPort` = `8766`, `serverPath` = `/ws`.

If this PC's LAN IP changes (different network, DHCP renewal), update
`serverIp` on the script in Lens Studio and re-push the Lens to the device.

## Every-boot startup sequence

After a laptop restart, bring things up in this order:

```powershell
# 1. Start Docker Desktop (if not already running), then:
wsl -d Ubuntu -- bash -lc "cd '/mnt/c/Users/jakub/Documents/Alien Bazaar/w01-tek-alien-bazaar/ros/docker' && docker compose -f compose.yaml up -d"
```

```powershell
# 2. Launch the sim (leave this running in its own window/background job):
wsl -d Ubuntu -- docker exec wojtek_robot bash -c "source /opt/ros/jazzy/setup.bash; source /ros2_ws/install/setup.bash; exec ros2 run wojtek_bringup robot --sim --foxglove --policy /ros2_ws/policies/wojtek-quiet-locomotion-46b5f29"
```

Wait for `deck panel on http://0.0.0.0:8090` and controller
`Successfully switched controllers!` lines before continuing -- see
"Known issue" below if instead you see `Controller already loaded` /
`Failed to configure controller`.

```powershell
# 3. Launch the Spectacles bridge (also long-running, own window/job):
wsl -d Ubuntu -- docker exec wojtek_robot bash /ros2_ws/src/wojtek_spectacles_bridge/_run_bridge.sh
```

Look for `spectacles bridge listening on ws://0.0.0.0:8766/ws`.

```powershell
# 4. (Optional, if the Windows session is fresh) confirm the firewall/portproxy rules are still there:
Get-NetFirewallRule -DisplayName "Wojtek Sim - Spectacles Bridge"
netsh interface portproxy show all
```

If either is missing (e.g. after certain Windows updates), redo steps 3/4
of the one-time setup above.

Then:

- Open `http://localhost:8090` for the Deck dashboard. Click **Arm**, then
  **Stand**.
- Open Foxglove (`app.foxglove.dev`), connect to `ws://localhost:8765`,
  load the `ros/foxglove/layouts/e2e.json` layout.
- Put on the Spectacles (same WiFi network as this PC, e.g. `UNDEF_5G`),
  open the Lens, pinch and drag. `/cmd_vel` in Foxglove and the sim robot
  should respond.

## Known issue: "Controller already loaded" on relaunch

If you stop and restart the sim without fully killing the previous run
first, `ros2_control_node` can come up seeing stale controller state from
the old process and the spawner dies immediately, leaving `/joint_states`
and `/cmd_vel` never populated (Deck's Arm button stays disabled; Foxglove
shows red "no data" icons on those topics even though the connection
itself is fine).

Fix: don't try to kill individual `ros2 run`/`ros2 launch` processes inside
the container (killing the wrong one, e.g. PID 1's child, takes the whole
container down). Instead do a full container restart:

```powershell
wsl -d Ubuntu -- docker restart wojtek_robot
```

then repeat steps 2-3 of the every-boot sequence above.
