# Add joints (+Joint)

import sys
from pathlib import Path

# Ensure project root is on sys.path for imports
project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import tkinter as tk
try:
    from ..robot.link import Link
except ImportError:
    try:
        from C2C.robot.link import Link
    except ImportError:
        from robot.link import Link

class DefineRobotUI:
    def __init__(self, parent, robot, update_callback):
        self.robot = robot
        self.update_callback = update_callback

        self.frame = tk.Frame(parent)
        self.frame.pack(side=tk.LEFT, fill=tk.Y, padx=10)

        tk.Label(self.frame, text="Robot Definition").pack()

        self.length_entry = tk.Entry(self.frame)
        self.length_entry.insert(0, "10")
        self.length_entry.pack()

        self.motor_type = tk.StringVar(value="servo")
        tk.OptionMenu(self.frame, self.motor_type,
                      "servo", "stepper").pack()

        tk.Button(self.frame, text="+ Joint",
                  command=self.add_joint).pack(pady=5)

    def add_joint(self):
        length = self.length_entry.get()
        motor = self.motor_type.get()

        link = Link(length=length, motor_type=motor)
        self.robot.add_link(link)

        self.update_callback()

