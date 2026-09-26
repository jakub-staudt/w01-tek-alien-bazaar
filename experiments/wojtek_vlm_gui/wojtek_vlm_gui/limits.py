"""Everything the page touches on the ROS 2 graph, as plain constants.

The page is a client of wojtek_nav's vlm_brain_node and of the robot's
operator services, plus read-only looks at the camera's own JPEG and its
raw depth for the live views. It never publishes /cmd_vel. No ROS import here; tested
model-free.
"""

from __future__ import annotations

# --- the brain (ros/src/wojtek_nav/wojtek_nav/vlm_brain_node.py) -------------

INSTRUCTION_TOPIC = "/wojtek/vlm/instruction"   # std_msgs/String: a task; "" or "stop" cancels
CANCEL_TOPIC = "/wojtek/nav/cancel"              # std_msgs/Empty: goto and the resolver drop their goal
VLM_STATUS_TOPIC = "/wojtek/vlm/status"          # std_msgs/String, JSON per step, latched
ANNOTATED_TOPIC = "/wojtek/vlm/annotated"        # sensor_msgs/Image rgb8, the picture with the model's point
GOTO_STATUS_TOPIC = "/wojtek/nav/status"         # std_msgs/String, latched: idle/turning/driving/blocked/reached
PIXEL_STATUS_TOPIC = "/wojtek/nav/pixel_status"  # std_msgs/String, latched: resolving/.../reached/blocked/...

# --- the camera (wojtek_perception_bringup on the robot, sim_camera_node) ----

# The camera node's own JPEG, the same stream the brain reads: shown live
# in the page's camera panel. Added 2026-09-26 for the bench, where the
# page runs ON the RPi next to the camera, so the frames cross no wifi
# link; on a PC page over the robot's AP this is a second reader of the
# stream (tens of KB a frame at 640x480, the size the deck streams).
CAMERA_TOPIC = "/camera/camera/color/image_raw/compressed"   # sensor_msgs/CompressedImage, jpeg

# The raw depth (16UC1, millimetres), shown colourised under the camera. Raw,
# not compressedDepth: PNG-encoding it would cost the RPi the CPU the bench
# saves; the cable carries 480x270x2 B at 20 fps (~5 MB/s) without trouble.
DEPTH_TOPIC = "/camera/camera/depth/image_rect_raw"          # sensor_msgs/Image, 16UC1
DEPTH_ENCODINGS = ("16UC1", "mono16")

# --- the walker (wojtek_vlm_gui/walker_node.py, the bench's legs) -----------

# std_msgs/String, JSON of walker.Walker.guide(), 10 Hz: what the person
# carrying the camera should do now (the drive command as words and an
# arrow, the turn so far, the goal from where the robot stands).
GUIDE_TOPIC = "/wojtek/walker/guide"
GOAL_TOPIC = "/wojtek/nav/goal"                   # geometry_msgs/PoseStamped, goto's setpoint (read by the walker)

# --- the robot's load (wojtek_vlm_gui/sysmon_node.py, run ON the RPi) ---------

# std_msgs/String, the JSON of sysmon.Snapshot, best effort, once a second: the
# page's Computer panel. The page runs off the robot; this is the one
# reading that has to come from it.
SYSMON_TOPIC = "/wojtek/sys/stat"
SYSMON_PERIOD_S = 1.0

# The brain's own stop words (vlm_brain_node.STOP_WORDS), kept verbatim so
# the page and the brain agree on what cancels a task.
STOP_WORDS = ("", "stop", "stój", "stop.")

# The brain subscribes to the instruction topic only while it runs; a task
# sent to nobody must be an error in the page, never a silent no-op. Over
# the robot's AP a subscription shows up a couple of seconds after the
# publisher is created (measured with text_commander), hence the wait.
SUBSCRIBER_WAIT_S = 5.0
SUBSCRIBER_POLL_S = 0.1

# --- the robot's operator services (wojtek_bringup real_io / policy_node) ---

ARM_SERVICE = "/wojtek/arm"            # std_srvs/SetBool: targets reach the motors only while armed
POLICY_SERVICE = "/wojtek/enable"      # std_srvs/SetBool: the RL gait computes targets only while enabled
STAND_UP_SERVICE = "/wojtek/stand_up"  # std_srvs/Trigger: slow ramp to the home pose (refused while armed)
LIE_DOWN_SERVICE = "/wojtek/lie_down"  # std_srvs/Trigger: slow ramp to the folded pose (refused while armed)

# What the page may write. Anything else that moves or arms the robot is
# outside its contract: /cmd_vel belongs to the drive sources (pad, Deck,
# consoles, text_commander, goto, the brain's turns).
WRITABLE_TOPICS = (INSTRUCTION_TOPIC, CANCEL_TOPIC)
WRITABLE_SERVICES = (ARM_SERVICE, POLICY_SERVICE, STAND_UP_SERVICE, LIE_DOWN_SERVICE)
NEVER_PUBLISHED = ("/cmd_vel", "/wojtek/joint_targets", "/wojtek/nav/goal", "/wojtek/nav/pixel_goal")
