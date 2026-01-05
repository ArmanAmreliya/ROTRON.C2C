# 2-D robot view

import tkinter as tk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

class RobotView2D:
    def __init__(self, parent):
        self.fig = Figure(figsize=(4, 4))
        self.ax = self.fig.add_subplot(111)

        self.canvas = FigureCanvasTkAgg(self.fig, master=parent)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def update(self, points):
        self.ax.clear()
        xs, ys, _ = zip(*points)

        self.ax.plot(xs, ys, marker="o", linewidth=2, markersize=6)
        
        # Dynamic bounds with padding
        x_min, x_max = min(xs), max(xs)
        y_min, y_max = min(ys), max(ys)
        
        # Add 20% padding
        x_range = max(x_max - x_min, 10)
        y_range = max(y_max - y_min, 10)
        x_pad = x_range * 0.2
        y_pad = y_range * 0.2
        
        self.ax.set_xlim(x_min - x_pad, x_max + x_pad)
        self.ax.set_ylim(y_min - y_pad, y_max + y_pad)
        self.ax.set_aspect("equal")
        self.ax.grid(True, alpha=0.3)

        self.canvas.draw()

