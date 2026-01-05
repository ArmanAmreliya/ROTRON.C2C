"""
Command Builder - Converts joint angles to ESP32-compatible motion frames

CRITICAL RULES:
1. ESP32 NEVER calculates kinematics
2. ALL motion must be structured joint commands
3. No JSON - line-by-line parsing only
4. No floating-point dependency
5. Clear start/end markers ($MOVE ... $)

Command Format:
$MOVE
J1:90
J2:120
J3:45
SPD:30
TIME:100
$
"""


def generate_move_command(robot_model, speed=30, time_ms=100, weld_state=None):
    """
    Generate ESP32-compatible MOVE command from current robot state.
    
    Args:
        robot_model: RobotModel instance with links containing current angles
        speed: Movement speed (0-100)
        time_ms: Time to complete movement in milliseconds
        weld_state: Welding state - "ON", "OFF", or None (no welding)
    
    Returns:
        str: Formatted command string ready for ESP32
    
    Example:
        >>> robot = RobotModel()
        >>> robot.links = [Link(...), Link(...)]
        >>> cmd = generate_move_command(robot, speed=30, time_ms=100)
        >>> print(cmd)
        $MOVE
        J1:90
        J2:120
        SPD:30
        TIME:100
        $
        
        >>> # With welding
        >>> cmd = generate_move_command(robot, speed=30, time_ms=100, weld_state="ON")
        >>> print(cmd)
        $MOVE
        J1:90
        J2:120
        SPD:30
        WELD:ON
        TIME:100
        $
    """
    if not robot_model.links:
        return None
    
    lines = ["$MOVE"]
    
    # Add joint angles (convert to integers for ESP32)
    for i, link in enumerate(robot_model.links):
        # Round to nearest integer - ESP32 doesn't need sub-degree precision
        angle = int(round(link.angle))
        lines.append(f"J{i+1}:{angle}")
    
    # Add speed
    lines.append(f"SPD:{int(speed)}")
    
    # Add welding state (if specified)
    # CRITICAL: WELD must come BEFORE TIME in command structure
    if weld_state:
        weld_state = str(weld_state).upper()
        if weld_state in ["ON", "OFF"]:
            lines.append(f"WELD:{weld_state}")
    
    # Add time
    lines.append(f"TIME:{int(time_ms)}")
    
    # End marker
    lines.append("$")
    
    return "\n".join(lines)


def generate_stop_command():
    """
    Generate emergency stop command.
    
    Returns:
        str: Emergency stop command
    
    Example:
        >>> cmd = generate_stop_command()
        >>> print(cmd)
        $STOP$
    """
    return "$STOP$"


def generate_home_command():
    """
    Generate home position command (all joints to safe position).
    
    Returns:
        str: Home command
    
    Example:
        >>> cmd = generate_home_command()
        >>> print(cmd)
        $HOME$
    """
    return "$HOME$"


def generate_status_request():
    """
    Generate status request command.
    
    Returns:
        str: Status request command
    
    Example:
        >>> cmd = generate_status_request()
        >>> print(cmd)
        $STATUS?$
    """
    return "$STATUS?$"


def validate_command(command_string):
    """
    Validate that command string follows ESP32 protocol.
    
    Args:
        command_string: Command to validate
    
    Returns:
        tuple: (bool: is_valid, str: error_message or None)
    
    Example:
        >>> valid, error = validate_command("$MOVE\\nJ1:90\\n$")
        >>> print(valid)
        True
    """
    if not command_string:
        return False, "Command is empty"
    
    # Check start marker
    if not command_string.startswith("$"):
        return False, "Command must start with $"
    
    # Check end marker
    if not command_string.endswith("$"):
        return False, "Command must end with $"
    
    # For MOVE commands, verify structure
    if "$MOVE" in command_string:
        lines = command_string.strip().split("\n")
        
        if len(lines) < 3:
            return False, "MOVE command too short"
        
        # Check for at least one joint
        has_joint = any(line.startswith("J") for line in lines)
        if not has_joint:
            return False, "MOVE command must have at least one joint"
        
        # Check for required parameters
        has_speed = any(line.startswith("SPD:") for line in lines)
        has_time = any(line.startswith("TIME:") for line in lines)
        
        if not has_speed:
            return False, "MOVE command must have SPD parameter"
        if not has_time:
            return False, "MOVE command must have TIME parameter"
    
    return True, None


def parse_command_log(log_text):
    """
    Parse a log of commands to extract motion sequence.
    
    Args:
        log_text: Multi-line string of logged commands
    
    Returns:
        list: List of parsed command dictionaries
    
    Example:
        >>> log = "$MOVE\\nJ1:90\\nJ2:120\\nSPD:30\\nTIME:100\\n$"
        >>> commands = parse_command_log(log)
        >>> print(commands[0])
        {'type': 'MOVE', 'joints': {1: 90, 2: 120}, 'speed': 30, 'time': 100}
    """
    commands = []
    current_command = []
    
    for line in log_text.split("\n"):
        line = line.strip()
        
        if line.startswith("$") and line != "$":
            # Start of command
            current_command = [line]
        elif line == "$":
            # End of command
            current_command.append(line)
            # Parse the command
            cmd = _parse_single_command("\n".join(current_command))
            if cmd:
                commands.append(cmd)
            current_command = []
        elif current_command:
            # Middle of command
            current_command.append(line)
    
    return commands


def _parse_single_command(command_string):
    """
    Parse a single command string into dictionary.
    
    Internal helper function.
    """
    lines = command_string.strip().split("\n")
    
    if not lines:
        return None
    
    cmd_type = lines[0].replace("$", "").strip()
    
    if cmd_type == "MOVE":
        cmd = {
            'type': 'MOVE',
            'joints': {},
            'speed': None,
            'time': None,
            'weld': None
        }
        
        for line in lines[1:-1]:  # Skip first and last ($)
            if line.startswith("J"):
                # Parse joint: J1:90
                parts = line.split(":")
                if len(parts) == 2:
                    joint_num = int(parts[0][1:])  # Remove 'J'
                    angle = int(parts[1])
                    cmd['joints'][joint_num] = angle
            elif line.startswith("SPD:"):
                cmd['speed'] = int(line.split(":")[1])
            elif line.startswith("WELD:"):
                cmd['weld'] = line.split(":")[1]
            elif line.startswith("TIME:"):
                cmd['time'] = int(line.split(":")[1])
        
        return cmd
    
    elif cmd_type in ["STOP", "HOME", "STATUS?"]:
        return {'type': cmd_type}
    
    return None


def format_command_for_display(command_string):
    """
    Format command string for human-readable display.
    
    Args:
        command_string: Raw command string
    
    Returns:
        str: Formatted display string
    
    Example:
        >>> cmd = "$MOVE\\nJ1:90\\nJ2:120\\nSPD:30\\nTIME:100\\n$"
        >>> print(format_command_for_display(cmd))
        📤 MOVE Command:
           Joint 1 → 90°
           Joint 2 → 120°
           Speed: 30
           Time: 100ms
    """
    parsed = _parse_single_command(command_string)
    
    if not parsed:
        return command_string
    
    if parsed['type'] == 'MOVE':
        lines = [f"📤 MOVE Command:"]
        for joint_num in sorted(parsed['joints'].keys()):
            angle = parsed['joints'][joint_num]
            lines.append(f"   Joint {joint_num} → {angle}°")
        lines.append(f"   Speed: {parsed['speed']}")
        if parsed.get('weld'):
            weld_icon = "🔥" if parsed['weld'] == "ON" else "❄"
            lines.append(f"   {weld_icon} Weld: {parsed['weld']}")
        lines.append(f"   Time: {parsed['time']}ms")
        return "\n".join(lines)
    
    elif parsed['type'] == 'STOP':
        return "🚨 EMERGENCY STOP Command"
    
    elif parsed['type'] == 'HOME':
        return "🏠 HOME Position Command"
    
    elif parsed['type'] == 'STATUS?':
        return "❓ STATUS Request"
    
    return command_string


# Export validation
if __name__ == "__main__":
    # Test command generation
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
    cmd = generate_move_command(robot, speed=30, time_ms=100)
    print("Generated Command:")
    print(cmd)
    print()
    
    # Validate
    valid, error = validate_command(cmd)
    print(f"Valid: {valid}")
    if error:
        print(f"Error: {error}")
    print()
    
    # Display format
    print(format_command_for_display(cmd))
    print()
    
    # Test emergency stop
    stop_cmd = generate_stop_command()
    print(f"Stop Command: {stop_cmd}")
    print()
    
    # Parse
    parsed = parse_command_log(cmd)
    print(f"Parsed: {parsed}")
