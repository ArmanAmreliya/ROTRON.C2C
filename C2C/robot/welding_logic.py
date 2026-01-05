"""
Welding Logic Engine

Generates welding motion sequences for spot and continuous welding.
All welding commands are embedded in $MOVE frames - never standalone.

CRITICAL RULES:
1. Welding state (ON/OFF) always part of motion command
2. ESP32 never decides welding logic - only toggles GPIO
3. PC calculates all weld points, timing, and sequences
4. Emergency stop sets WELD:OFF
5. Same command stream to simulation and ESP32

WELDING MODES:
1. Spot Welding - Move to point, weld, retract, repeat
2. Continuous Welding - Weld while following path continuously
"""

import math
import time
try:
    from ..robot.command_builder import generate_move_command
except ImportError:
    try:
        from C2C.robot.command_builder import generate_move_command
    except ImportError:
        from robot.command_builder import generate_move_command


class WeldingEngine:
    """
    PC-side welding logic engine.
    
    Generates motion sequences with embedded welding control.
    Never sends standalone GPIO commands - always part of motion.
    """
    
    def __init__(self, robot_model):
        """
        Initialize welding engine.
        
        Args:
            robot_model: RobotModel instance for motion generation
        """
        self.robot = robot_model
        
        # Welding parameters
        self.mode = "spot"  # "spot" or "continuous"
        
        # Spot welding parameters
        self.spot_weld_time = 500      # milliseconds
        self.spot_spacing = 5.0         # cm
        self.spot_retract_offset = 1.0  # cm
        
        # Continuous welding parameters
        self.continuous_speed = 30      # % of max speed
        self.continuous_path_delay = 100  # ms between path segments
        
        # State
        self.is_welding = False
        self.weld_points = []  # List of positions to weld
        self.current_weld_index = 0
    
    def set_spot_parameters(self, weld_time_ms, spacing_cm, retract_offset_cm):
        """
        Configure spot welding parameters.
        
        Args:
            weld_time_ms: Time to hold weld at each spot (milliseconds)
            spacing_cm: Distance between weld spots (centimeters)
            retract_offset_cm: Distance to retract after each weld (centimeters)
        """
        self.spot_weld_time = int(weld_time_ms)
        self.spot_spacing = float(spacing_cm)
        self.spot_retract_offset = float(retract_offset_cm)
        print(f"✅ Spot Welding: {weld_time_ms}ms, {spacing_cm}cm spacing, {retract_offset_cm}cm retract")
    
    def set_continuous_parameters(self, speed_percent, path_delay_ms):
        """
        Configure continuous welding parameters.
        
        Args:
            speed_percent: Welding speed as percentage (0-100)
            path_delay_ms: Delay between path segments (milliseconds)
        """
        self.continuous_speed = int(speed_percent)
        self.continuous_path_delay = int(path_delay_ms)
        print(f"✅ Continuous Welding: {speed_percent}% speed, {path_delay_ms}ms delay")
    
    def generate_spot_weld_sequence(self, weld_points):
        """
        Generate spot welding command sequence.
        
        For each point:
        1. Move to point (WELD:OFF)
        2. Weld at point (WELD:ON)
        3. Wait weld_time
        4. Stop welding (WELD:OFF)
        5. Retract by offset
        6. Move to next point
        
        Args:
            weld_points: List of (x, y, z) or joint angle dictionaries
        
        Returns:
            list: List of command strings
        """
        commands = []
        
        print(f"🔥 Generating spot weld sequence for {len(weld_points)} points")
        
        for i, point in enumerate(weld_points):
            # Set robot to weld point position
            self._set_robot_to_position(point)
            
            # 1. Move to weld point (WELD:OFF)
            cmd = generate_move_command(
                self.robot,
                speed=50,
                time_ms=500,
                weld_state="OFF"
            )
            commands.append(cmd)
            
            # 2. Start welding (WELD:ON) - stay at same position
            cmd_weld_on = generate_move_command(
                self.robot,
                speed=0,  # No movement
                time_ms=self.spot_weld_time,
                weld_state="ON"
            )
            commands.append(cmd_weld_on)
            
            # 3. Stop welding (WELD:OFF)
            cmd_weld_off = generate_move_command(
                self.robot,
                speed=0,
                time_ms=50,  # Quick command
                weld_state="OFF"
            )
            commands.append(cmd_weld_off)
            
            # 4. Retract (if not last point)
            if i < len(weld_points) - 1:
                self._retract_torch(self.spot_retract_offset)
                cmd_retract = generate_move_command(
                    self.robot,
                    speed=30,
                    time_ms=200,
                    weld_state="OFF"
                )
                commands.append(cmd_retract)
            
            print(f"  Point {i+1}/{len(weld_points)}: {len(commands)} commands generated")
        
        print(f"✅ Spot weld sequence complete: {len(commands)} total commands")
        return commands
    
    def generate_continuous_weld_sequence(self, path_points):
        """
        Generate continuous welding command sequence.
        
        1. Move to start (WELD:OFF)
        2. Start welding (WELD:ON)
        3. Follow path continuously (WELD:ON)
        4. End welding (WELD:OFF)
        
        Args:
            path_points: List of positions along weld path
        
        Returns:
            list: List of command strings
        """
        commands = []
        
        if not path_points:
            return commands
        
        print(f"🔥 Generating continuous weld sequence for {len(path_points)} path points")
        
        # 1. Move to start position (WELD:OFF)
        self._set_robot_to_position(path_points[0])
        cmd_start = generate_move_command(
            self.robot,
            speed=50,
            time_ms=500,
            weld_state="OFF"
        )
        commands.append(cmd_start)
        
        # 2. Start welding (WELD:ON)
        cmd_weld_on = generate_move_command(
            self.robot,
            speed=0,
            time_ms=100,
            weld_state="ON"
        )
        commands.append(cmd_weld_on)
        
        # 3. Follow path with welding ON
        for i, point in enumerate(path_points[1:], start=1):
            self._set_robot_to_position(point)
            
            # Calculate time based on distance and speed
            # (simplified - use actual path length in production)
            move_time = self.continuous_path_delay
            
            cmd = generate_move_command(
                self.robot,
                speed=self.continuous_speed,
                time_ms=move_time,
                weld_state="ON"  # Keep welding throughout path
            )
            commands.append(cmd)
            
            if (i % 10) == 0:
                print(f"  Progress: {i}/{len(path_points)} points")
        
        # 4. Stop welding (WELD:OFF)
        cmd_weld_off = generate_move_command(
            self.robot,
            speed=0,
            time_ms=50,
            weld_state="OFF"
        )
        commands.append(cmd_weld_off)
        
        print(f"✅ Continuous weld sequence complete: {len(commands)} total commands")
        return commands
    
    def generate_emergency_stop_sequence(self):
        """
        Generate emergency stop with welding OFF.
        
        Returns:
            list: Emergency stop commands
        """
        commands = []
        
        # Emergency stop with WELD:OFF
        cmd = generate_move_command(
            self.robot,
            speed=0,
            time_ms=0,
            weld_state="OFF"
        )
        commands.append(cmd)
        
        return commands
    
    def _set_robot_to_position(self, position):
        """
        Set robot to specified position.
        
        Args:
            position: Dictionary of joint angles or (x,y,z) tuple
        """
        if isinstance(position, dict):
            # Joint angles provided
            for joint_name, angle in position.items():
                # Find joint index (J1 -> 0, J2 -> 1, etc.)
                if joint_name.startswith('J'):
                    joint_idx = int(joint_name[1:]) - 1
                    if joint_idx < len(self.robot.links):
                        self.robot.links[joint_idx].angle = angle
        elif isinstance(position, (list, tuple)) and len(position) == 3:
            # Cartesian coordinates - would need IK
            # For now, use current angles (IK should be implemented separately)
            pass
    
    def _retract_torch(self, offset_cm):
        """
        Retract torch by specified offset.
        
        Simplified - moves last joint by offset.
        In production, use proper IK for Z-axis retraction.
        
        Args:
            offset_cm: Retraction distance in centimeters
        """
        # Simplified: Retract by moving last joint
        # In production: Calculate proper Z-axis retraction using IK
        if self.robot.links:
            # Move last link up slightly
            last_joint = self.robot.links[-1]
            last_joint.angle += 5  # Simplified retraction angle
    
    def interpolate_path_points(self, start_point, end_point, num_points=10):
        """
        Interpolate points along a path between start and end.
        
        Args:
            start_point: Starting position (dict of joint angles)
            end_point: Ending position (dict of joint angles)
            num_points: Number of interpolation points
        
        Returns:
            list: List of interpolated positions
        """
        points = []
        
        # Linear interpolation between start and end
        for i in range(num_points + 1):
            t = i / num_points  # Parameter from 0 to 1
            
            point = {}
            for joint_name in start_point.keys():
                start_angle = start_point[joint_name]
                end_angle = end_point[joint_name]
                interpolated_angle = start_angle + t * (end_angle - start_angle)
                point[joint_name] = interpolated_angle
            
            points.append(point)
        
        return points
    
    def calculate_weld_points_along_line(self, start, end, spacing_cm):
        """
        Calculate evenly-spaced weld points along a line.
        
        Args:
            start: Start position (dict or tuple)
            end: End position (dict or tuple)
            spacing_cm: Distance between weld points
        
        Returns:
            list: List of weld point positions
        """
        # Simplified - use interpolation
        # Calculate number of points based on spacing
        # (In production, use actual path length calculation)
        
        num_points = max(2, int(10 / spacing_cm))  # Rough estimate
        
        if isinstance(start, dict) and isinstance(end, dict):
            return self.interpolate_path_points(start, end, num_points)
        
        return []


# Testing
if __name__ == "__main__":
    print("Welding Engine Test")
    print("=" * 50)
    
    # Mock robot
    class MockLink:
        def __init__(self, angle):
            self.angle = angle
    
    class MockRobot:
        def __init__(self):
            self.links = [
                MockLink(90),
                MockLink(120),
                MockLink(45)
            ]
    
    robot = MockRobot()
    engine = WeldingEngine(robot)
    
    # Test spot welding
    print("\n[TEST 1] Spot Welding:")
    engine.set_spot_parameters(weld_time_ms=500, spacing_cm=5, retract_offset_cm=1)
    
    weld_points = [
        {'J1': 90, 'J2': 120, 'J3': 45},
        {'J1': 100, 'J2': 110, 'J3': 50},
        {'J1': 110, 'J2': 100, 'J3': 55}
    ]
    
    spot_commands = engine.generate_spot_weld_sequence(weld_points)
    print(f"\nGenerated {len(spot_commands)} commands")
    print("\nFirst command:")
    print(spot_commands[0])
    
    # Test continuous welding
    print("\n[TEST 2] Continuous Welding:")
    engine.set_continuous_parameters(speed_percent=30, path_delay_ms=100)
    
    path_points = engine.interpolate_path_points(
        {'J1': 90, 'J2': 120, 'J3': 45},
        {'J1': 120, 'J2': 90, 'J3': 60},
        num_points=10
    )
    
    continuous_commands = engine.generate_continuous_weld_sequence(path_points)
    print(f"\nGenerated {len(continuous_commands)} commands")
    print("\nFirst command:")
    print(continuous_commands[0])
    
    print("\n✅ Welding engine test complete!")
