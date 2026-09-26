"""Everything the page touches on the ROS 2 graph, as plain constants.

The page is a client of wojtek_nav's vlm_brain_node and of the robot's
operator services, nothing more. It never publishes /cmd_vel and never
subscribes to a camera topic. No ROS import here; tested model-free.
"""

from __future__ import annotations

# --- the brain (ros/src/wojtek_nav/wojtek_nav/vlm_brain_node.py) -------------

INSTRUCTION_TOPIC = "/wojtek/vlm/instruction"   # std_msgs/String: a task; "" or "stop" cancels
CANCEL_TOPIC = "/wojtek/nav/cancel"              # std_msgs/Empty: goto and the resolver drop their goal
VLM_STATUS_TOPIC = "/wojtek/vlm/status"          # std_msgs/String, JSON per step, latched
ANNOTATED_TOPIC = "/wojtek/vlm/annotated"        # sensor_msgs/Image rgb8, the picture with the model's point
GOTO_STATUS_TOPIC = "/wojtek/nav/status"         # std_msgs/String, latched: idle/turning/driving/blocked/reached
PIXEL_STATUS_TOPIC = "/wojtek/nav/pixel_status"  # std_msgs/String, latched: resolving/.../reached/blocked/...

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
