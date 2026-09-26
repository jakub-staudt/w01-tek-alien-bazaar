#!/bin/bash
source /opt/ros/jazzy/setup.bash
source /ros2_ws/install/setup.bash
export AMENT_PREFIX_PATH="/ros2_ws/install/wojtek_spectacles_bridge:$AMENT_PREFIX_PATH"
exec ros2 run wojtek_spectacles_bridge spectacles_bridge --ros-args -p port:=8766
