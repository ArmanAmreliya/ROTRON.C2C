"""Robot model made from links."""

import sys
from pathlib import Path

# Ensure project root is on sys.path for imports
project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

try:
    from .fk import forward_kinematics
except ImportError:
    try:
        from C2C.robot.fk import forward_kinematics
    except ImportError:
        from robot.fk import forward_kinematics

class RobotModel:
    def __init__(self):
        self.links = []

    def add_link(self, link):
        self.links.append(link)

    def get_points(self):
        return forward_kinematics(self.links)

    def get_tool_position(self):
        if not self.links:
            return (0, 0, 0)
        return self.get_points()[-1]

