cmake_minimum_required(VERSION 3.8)
project(tb4_assignment)

find_package(ament_cmake REQUIRED)

install(DIRECTORY launch config maps worlds
  DESTINATION share/${PROJECT_NAME}/
)

install(PROGRAMS
  scripts/navigate_goals.py
  scripts/record_goals.py
  scripts/yolo_detector.py
  scripts/gesture_recognition_node.py
  scripts/robot_behavior_node.py
  DESTINATION lib/${PROJECT_NAME}
)

install(FILES scripts/gesture_logic.py DESTINATION lib/${PROJECT_NAME})

ament_package()
