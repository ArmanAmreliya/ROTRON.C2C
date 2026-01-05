import sys
from pathlib import Path

# Ensure project root is on sys.path for imports
project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import tkinter as tk
try:
    from ..robot.ik import inverse_kinematics_xyz
except ImportError:
    try:
        from C2C.robot.ik import inverse_kinematics_xyz
    except ImportError:
        from robot.ik import inverse_kinematics_xyz

class CartesianControlUI:
    def __init__(self, parent, robot, update_callback):
        self.robot = robot
        self.update_callback = update_callback

        self.frame = tk.Frame(parent, bd=2, relief=tk.GROOVE)
        self.frame.pack(fill=tk.X, pady=5)

        tk.Label(self.frame, text="X").grid(row=0, column=0)
        tk.Label(self.frame, text="Y").grid(row=0, column=2)
        tk.Label(self.frame, text="Z").grid(row=0, column=4)

        self.x = tk.Entry(self.frame, width=6)
        self.y = tk.Entry(self.frame, width=6)
        self.z = tk.Entry(self.frame, width=6)

        self.x.insert(0, "10")
        self.y.insert(0, "10")
        self.z.insert(0, "10")

        self.x.grid(row=0, column=1)
        self.y.grid(row=0, column=3)
        self.z.grid(row=0, column=5)

        tk.Button(self.frame, text="MOVE XYZ",
                  command=self.move).grid(row=0, column=6, padx=10)

    def move(self):
        try:
            x = float(self.x.get())
            y = float(self.y.get())
            z = float(self.z.get())

            a1, a2, z_val = inverse_kinematics_xyz(
                x, y, z, self.robot.links
            )

            self.robot.links[0].angle = a1
            self.robot.links[1].angle = a2

            # Adjust remaining links vertically
            for i in range(2, len(self.robot.links)):
                self.robot.links[i].length = z_val / max(1, len(self.robot.links)-2)

            self.update_callback()

        except Exception as e:
            print("XYZ ERROR:", e)
