# Link definition for robot

class Link:
    def __init__(self, length, motor_type="servo",
                 min_angle=0, max_angle=180, rotation_axis="Z"):
        self.length = float(length)
        self.motor_type = motor_type
        self.min_angle = min_angle
        self.max_angle = max_angle
        self.rotation_axis = rotation_axis.upper()  # X, Y, or Z

        # Servo centered, stepper starts at 0
        if motor_type == "servo":
            self.angle = (min_angle + max_angle) / 2
        else:
            self.angle = 0
