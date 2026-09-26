# Experiment: the operator GUI for Wojtek's VLM brain

> **Status: EXPERIMENTAL. Not production; nothing here is deployed to the robot.**
> Nothing here is deployed by `ros/deploy.sh`, and no package here is a
> dependency of `wojtek_bringup`. It runs on the PC next to the simulation
> or next to the robot's ROS 2 graph; launching, arming and disarming the
> robot remain human actions. Interfaces are unstable by definition.

A Streamlit page on http://localhost:8501 where the operator types a task
("go to the purple pillar"), watches Wojtek's VLM brain work through it
step by step, and keeps the robot's Stand up / Arm / Disarm buttons under
their hand. The brain is `wojtek_nav`'s `vlm_brain_node`
([ros/src/wojtek_nav/README.md](../../ros/src/wojtek_nav/README.md)): it
reads the camera, asks the model, verifies, hands pixels to the resolver
and setpoints to `goto`, and turns to search. This page does none of that.
It is a thin ROS 2 client: two topics out, four topics in, four operator
services.

## How it is wired

```
 operator ──► Streamlit :8501 (this experiment, its own container)
                │ task ─────────► /wojtek/vlm/instruction (String) ──► vlm_brain_node ── /v1/chat/completions ──► Ollama on the DGX
                │ STOP ─────────► /wojtek/nav/cancel (Empty) + "" instruction           │ pixel
                │ step log ◄──── /wojtek/vlm/status (JSON, latched)                     ▼
                │ picture ◄───── /wojtek/vlm/annotated (one frame per model call)  pixel_goal_node ──► /wojtek/nav/goal ──► goto_node ──► /cmd_vel
                │ words ◄─────── /wojtek/nav/status, /wojtek/nav/pixel_status           costmap (odom, 6 x 6 m) ──────────┘
                └ Robot buttons ► /wojtek/stand_up, lie_down, arm, enable (services); Disarm and Lie down also send STOP

 pad, Steam Deck, web console, text_commander ──► /cmd_vel too: policy_node keeps the last message, 0.5 s dead-man
```

- The page never publishes `/cmd_vel` and never subscribes to a camera
  topic (`wojtek_vlm_gui/limits.py` lists everything it touches; the
  tests assert the publisher and subscription sets). The only picture it
  shows is the frame the brain annotated, one per model call, which
  travels between two processes on the PC, never across the robot's WiFi.
- The model route is the brain's, not the page's: `VLM_URL` and
  `VLM_MODEL` in the repo-root `.env`, read by `ros/sim.sh` into the
  `wojtek_robot` container and by `brain.launch.py`. The only inference
  route is Ollama on the DGX, reached through an ssh tunnel from the PC.
- Arming stays a human button. Disarm and Lie down also STOP the brain,
  because disarming stops the motors, not a task that would otherwise
  keep publishing goals into a disarmed robot.

## Run it (simulation)

```bash
# 0. once per machine
./experiments/wojtek_vlm_gui/run.sh build

# 1. every session: the tunnel to the DGX's Ollama (alias in your ssh config, never in the tree)
ssh -f -N -L 11435:127.0.0.1:11434 <dgx alias>
curl -s http://127.0.0.1:11435/api/tags | head -c 200      # the model tag must be listed
#    root .env: VLM_URL=http://host.docker.internal:11435  VLM_MODEL=qwen3-vl:30b-a3b-instruct

# 2. the sim with Pawel's nav stack and the brain
./ros/sim.sh model_xml:=scene_nav.xml leg_odom:=true nav:=true vlm:=true

# 3. the page
./experiments/wojtek_vlm_gui/run.sh gui        # http://localhost:8501
```

In the page: `Stand up`, then `Arm`, then type the task. Use the
`-instruct` model tags only: Ollama ignores `think=false` on the thinking
tags and every step pays a hidden preamble.

## The rule with the pad and the Deck

`/cmd_vel` is shared by every drive source, and `policy_node` keeps
whichever message came last. While a brain task drives, a stick or the
Deck's gate publishes into the same topic and the robot alternates between
the two. **STOP the brain before driving by hand.** Disarm from anywhere
(pad A, the Deck, this page) stops the motors; only this page's Disarm
also ends the task.

## What the page shows

| element | source |
|---|---|
| one line per step: `#3 ask {"type":"goal",...} 1.2s`, `#3 verify ...`, `#3 pixel_goal -> reached target 0.85 m`, `#4 turn 45.0deg (total 90deg)` | `/wojtek/vlm/status` |
| the picture under each `ask` line, with the model's point drawn by the brain | `/wojtek/vlm/annotated` |
| `finished: done` in green, any other result (`gave_up`, `cancelled`, `replaced`, `error ...`, `timeout`) in red | the finishing status |
| `goto: driving`, `pixel: sent` in the sidebar | `/wojtek/nav/status`, `/wojtek/nav/pixel_status` |
| the robot's own answer after every Robot button | the services' responses |

A task typed while nobody subscribes to the instruction topic (no session
with `vlm:=true`) is refused in the page with a message, never dropped
silently. A stop word (`stop`, empty, the brain's own `stój`) typed as a
task is a STOP.

## Layout

| path | purpose |
|---|---|
| `run.sh` | `build \| up \| down \| shell \| gui \| test` |
| `docker/` | the `wojtek_vlm_gui` image (ros:jazzy-ros-base + a Streamlit venv) and compose service (host net, the sim's DDS settings) |
| `wojtek_vlm_gui/limits.py` | every topic and service the page touches; what it never publishes |
| `wojtek_vlm_gui/task_log.py` | the brain's status stream as the page prints it (pure) |
| `wojtek_vlm_gui/brain_client.py` | the ROS 2 node: instruction and cancel out, status and picture in |
| `wojtek_vlm_gui/arm_switch.py` | the operator's service calls |
| `wojtek_vlm_gui/app.py` | the page |
| `tests/` | model-free: the log, the client against a mock node, the switch, the hygiene guard |

```bash
./experiments/wojtek_vlm_gui/run.sh test                      # in the container
EXP_PY=<python with pytest> ./experiments/wojtek_vlm_gui/run.sh test   # on the host: the ROS-free tests, the rest skipped
```

## Isolation rules

1. Nothing outside this directory imports anything inside it, and nothing
   in the root markdown, `ros/`, `training/` or `docs/` names this
   directory (`tests/test_repo_hygiene.py`).
2. `ros/sim.sh`, `ros/dev.sh`, `ros/docker/compose.yaml` are untouched; this
   experiment runs its own compose project next to them.
3. No secrets and no private host identities in the tree: the DGX alias is
   the operator's ssh config, the model endpoint is the gitignored `.env`.

## Physical robot (human-authorized)

The page talks to the robot's graph over the WiFi AP exactly as it talks
to the sim, with the brain running on the PC (`ros2 run wojtek_bringup
robot --web-console --vlm`, the RPi stack with `perception:=true
nav:=true`). Launching, arming and disarming stay human actions outside
this experiment. Not run yet.
