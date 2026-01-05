# 3-D robot view

import tkinter as tk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

class RobotView3D:
    def __init__(self, parent):
        self.fig = Figure(figsize=(4, 4))
        self.ax = self.fig.add_subplot(111, projection="3d")

        self.canvas = FigureCanvasTkAgg(self.fig, master=parent)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def update(self, points):
        self.ax.clear()
        xs, ys, zs = zip(*points)

        self.ax.plot(xs, ys, zs, marker="o", linewidth=2, markersize=6)
        
        # Dynamic bounds with padding
        x_min, x_max = min(xs), max(xs)
        y_min, y_max = min(ys), max(ys)
        z_min, z_max = min(zs), max(zs)
        
        # Add 20% padding
        x_range = max(x_max - x_min, 10)
        y_range = max(y_max - y_min, 10)
        z_range = max(z_max - z_min, 10)
        x_pad = x_range * 0.2
        y_pad = y_range * 0.2
        z_pad = z_range * 0.2
        
        self.ax.set_xlim(x_min - x_pad, x_max + x_pad)
        self.ax.set_ylim(y_min - y_pad, y_max + y_pad)
        self.ax.set_zlim(z_min - z_pad, z_max + z_pad)

        self.ax.set_xlabel("X")
        self.ax.set_ylabel("Y")
        self.ax.set_zlabel("Z")
        self.ax.grid(True, alpha=0.3)

        self.canvas.draw()

