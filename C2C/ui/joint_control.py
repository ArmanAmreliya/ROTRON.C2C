import tkinter as tk

class JointControlUI:
    def __init__(self, parent, robot, update_callback):
        self.robot = robot
        self.update_callback = update_callback
        self.frame = tk.Frame(parent)
        self.frame.pack(side=tk.LEFT, fill=tk.Y, padx=10)

        tk.Label(self.frame, text="Joint Control").pack()

        self.sliders = []
        for i, link in enumerate(robot.links):
            s = tk.Scale(
                self.frame,
                from_=link.min_angle,
                to=link.max_angle,
                orient=tk.HORIZONTAL,
                label=f"Joint {i+1}",
                command=self.on_change
            )
            s.set(link.angle)
            s.pack(fill=tk.X)
            self.sliders.append(s)

    def on_change(self, value):
        for i, s in enumerate(self.sliders):
            self.robot.links[i].angle = s.get()
        self.update_callback()

    def refresh(self):
        for w in self.frame.winfo_children():
            w.destroy()
        self.__init__(self.frame.master, self.robot, self.update_callback)
