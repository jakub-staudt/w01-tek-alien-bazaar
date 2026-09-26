---
name: wojtek-vlm-gui
description: Run and drive the operator GUI for Wojtek's VLM brain -- the Streamlit page in experiments/wojtek_vlm_gui that sends a task to wojtek_nav's vlm_brain_node and shows its step log -- against the MuJoCo sim or, with human authorization, the physical robot. Use when asked to "tell Wojtek where to go", open the VLM page, run a VLM session, or check the brain's steps.
---

# The VLM GUI (experiments/wojtek_vlm_gui)

A Streamlit page on http://localhost:8501 where the operator types a task
and watches Wojtek's VLM brain work through it. Every inference and motion
decision is the brain's (`ros/src/wojtek_nav`, `vlm_brain_node`,
`pixel_goal_node`, `goto_node`, the costmap); the page is a thin ROS 2
client that publishes the instruction and the cancel and shows the brain's
status and the picture it answered on. It composes no prompt, calls no
model, publishes no `/cmd_vel` and reads no camera stream.

Read `experiments/wojtek_vlm_gui/README.md` for the wiring and
`ros/src/wojtek_nav/README.md` for the brain; this skill is the operating
procedure. Its own isolation test forbids the directory name in the root
markdown, `ros/`, `training/` and `docs/`; `skills/` is exempt, which is
why this guide lives here.

## Session, simulation

1. The only inference route is Ollama on the DGX, through an ssh tunnel
   from the PC. The alias is in the operator's ssh config, never in the
   tree. Check it before anything else:

   ```bash
   ssh -f -N -L 11435:127.0.0.1:11434 <dgx alias>
   curl -s http://127.0.0.1:11435/api/tags | head -c 300   # the -instruct tag must be listed
   ```

   Root `.env`: `VLM_URL=http://host.docker.internal:11435`,
   `VLM_MODEL=qwen3-vl:30b-a3b-instruct`, plus `HF_ORGANIZATION` and
   `HF_TOKEN` (the sim refuses to start without a policy reference). If
   the tunnel fails with a Cloudflare Access handshake error, the operator
   has to re-login on the PC; there is no fallback route, the session waits.
2. The sim with the nav stack and the brain:
   `./ros/sim.sh model_xml:=scene_nav.xml leg_odom:=true nav:=true vlm:=true`
3. The page: `./experiments/wojtek_vlm_gui/run.sh gui` (first time on a
   machine: `run.sh build`). Open http://localhost:8501.
4. In the page: `Stand up`, `Arm`, then type the task in English, e.g.
   "go to the purple pillar". The step log fills as the brain works;
   `finished: done` is green, anything else red with the reason.

If `Arm` refuses with a joint displacement just over 0.15 rad (the sim's
soft PD servo sags), loosen it for the session inside `./ros/dev.sh`:
`ros2 param set /wojtek_real_io max_arm_jump_rad 0.3`.

## The rule with the pad and the Deck

`/cmd_vel` is shared by every drive source and `policy_node` keeps the
last message. **STOP the brain before driving with the pad or the Deck.**
Disarm from anywhere stops the motors; the page's Disarm and Lie down also
end the brain's task. A task typed while no brain subscribes is refused
with a message, never dropped silently.

## Physical robot: human-authorized only

Never start this against the real robot on your own initiative. When the
user authorizes a robot session, the robot stack is launched, armed and
disarmed by the human; the brain runs on the PC next to the model
(`ros2 run wojtek_bringup robot --web-console --vlm`), the page in its
container talks over the WiFi AP. Not run yet.

## Validate a change

```bash
./experiments/wojtek_vlm_gui/run.sh test                    # in the container: all tests
EXP_PY=<python with pytest> ./experiments/wojtek_vlm_gui/run.sh test   # host: the ROS-free tests, the rest skipped
cd ros/src/wojtek_nav && PYTHONPATH=$PWD:$PYTHONPATH python3 -m pytest test/ -q   # the brain's own tests, untouched
```

Keep `tests/test_repo_hygiene.py` green: link to this skill from the root
docs, never to the experiment directory.

## Traps

- `ros/sim.sh` exits at once without `HF_ORGANIZATION`/`HF_TOKEN` (or
  `WOJTEK_POLICY`, or `policy:=`).
- The brain's annotated picture is a raw `rgb8` Image (2.7 MB at
  1280x720, one per model call); it stays on the PC between the brain and
  the page. Do not add a camera subscription to the page: a third reader
  of the colour stream is what starved the robot's link before.
- On hosts where CycloneDDS multicast loopback is broken, export
  `ROS_LOCALHOST_ONLY=1` for both the sim and the page containers.
- The web console (http://localhost:8080) still has its own brain panel
  from `wojtek_pc`; it publishes the same topics and is a debugging
  fallback, not the operator's page.

## Related

- `experiments/wojtek_vlm_gui/README.md` — wiring, what the page shows, run and test commands
- `ros/src/wojtek_nav/README.md` — the brain, the pixel resolver, goto, the costmap, their measurements
- `ros/src/wojtek_nav/wojtek_nav/vlm_brain.py` — the prompts, the schemas, the exploration policy
