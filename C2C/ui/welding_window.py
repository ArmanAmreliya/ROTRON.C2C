"""
Welding Control Panel - Industrial Welding GUI

Modal window for controlling robotic welding operations.
Supports spot welding and continuous welding modes.

CRITICAL RULES:
1. Never send standalone GPIO commands
2. All welding control embedded in $MOVE frames
3. Emergency stop immediately sets WELD:OFF
4. Same commands to simulation and ESP32
5. All welding logic calculated on PC, not ESP32
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading

try:
    from ..robot.welding_logic import WeldingEngine
    from ..hardware.esp32_comm import get_esp32_communicator
except ImportError:
    try:
        from C2C.robot.welding_logic import WeldingEngine
        from C2C.hardware.esp32_comm import get_esp32_communicator
    except ImportError:
        from robot.welding_logic import WeldingEngine
        from hardware.esp32_comm import get_esp32_communicator


class WeldingWindow:
    """
    Welding Control Panel GUI.
    
    Provides interface for spot and continuous welding operations.
    Generates motion sequences with embedded welding control.
    """
    
    def __init__(self, parent, robot_model, update_callback=None):
        """
        Initialize welding control panel.
        
        Args:
            parent: Parent Tkinter window
            robot_model: RobotModel instance
            update_callback: Callback to update main UI visualization
        """
        self.robot = robot_model
        self.update_callback = update_callback
        self.welding_engine = WeldingEngine(robot_model)
        self.esp32 = get_esp32_communicator()
        
        # Welding state
        self.is_welding_active = False
        self.weld_thread = None
        
        # Create modal window
        self.window = tk.Toplevel(parent)
        self.window.title("Welding Control Panel")
        self.window.geometry("600x700")
        self.window.configure(bg='#1a1a1a')
        
        # Make modal
        self.window.transient(parent)
        self.window.grab_set()
        
        # Emergency stop binding
        self.window.bind('<Control-s>', lambda e: self.emergency_stop())
        
        self._create_widgets()
        
        print("✅ Welding Control Panel opened")
    
    def _create_widgets(self):
        """Create GUI layout."""
        main_frame = tk.Frame(self.window, bg='#1a1a1a')
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # ===== TITLE =====
        title = tk.Label(
            main_frame,
            text="🔥 Welding Control Panel",
            font=('Arial', 18, 'bold'),
            bg='#1a1a1a',
            fg='#ff6600'
        )
        title.pack(pady=(0, 20))
        
        # ===== WELDING MODE SELECTION =====
        mode_frame = tk.LabelFrame(
            main_frame,
            text="Welding Type",
            font=('Arial', 12, 'bold'),
            bg='#2a2a2a',
            fg='white',
            padx=15,
            pady=15
        )
        mode_frame.pack(fill=tk.X, pady=(0, 15))
        
        self.mode_var = tk.StringVar(value="spot")
        
        spot_radio = tk.Radiobutton(
            mode_frame,
            text="Spot Welding",
            variable=self.mode_var,
            value="spot",
            font=('Arial', 11),
            bg='#2a2a2a',
            fg='white',
            selectcolor='#3a3a3a',
            activebackground='#2a2a2a',
            activeforeground='white',
            command=self._on_mode_change
        )
        spot_radio.pack(anchor=tk.W, pady=5)
        
        continuous_radio = tk.Radiobutton(
            mode_frame,
            text="Continuous Welding",
            variable=self.mode_var,
            value="continuous",
            font=('Arial', 11),
            bg='#2a2a2a',
            fg='white',
            selectcolor='#3a3a3a',
            activebackground='#2a2a2a',
            activeforeground='white',
            command=self._on_mode_change
        )
        continuous_radio.pack(anchor=tk.W, pady=5)
        
        # ===== SPOT WELDING SETTINGS =====
        self.spot_frame = tk.LabelFrame(
            main_frame,
            text="Spot Welding Settings",
            font=('Arial', 12, 'bold'),
            bg='#2a2a2a',
            fg='white',
            padx=15,
            pady=15
        )
        self.spot_frame.pack(fill=tk.X, pady=(0, 15))
        
        # Weld Time
        self._create_parameter_input(
            self.spot_frame,
            "Weld Time (ms):",
            "spot_weld_time",
            500,
            "Duration to hold weld at each spot"
        )
        
        # Spacing
        self._create_parameter_input(
            self.spot_frame,
            "Spacing (cm):",
            "spot_spacing",
            5.0,
            "Distance between weld points"
        )
        
        # Retract Offset
        self._create_parameter_input(
            self.spot_frame,
            "Retract Offset (cm):",
            "spot_retract",
            1.0,
            "Distance to retract after each weld"
        )
        
        # ===== CONTINUOUS WELDING SETTINGS =====
        self.continuous_frame = tk.LabelFrame(
            main_frame,
            text="Continuous Welding Settings",
            font=('Arial', 12, 'bold'),
            bg='#2a2a2a',
            fg='white',
            padx=15,
            pady=15
        )
        self.continuous_frame.pack(fill=tk.X, pady=(0, 15))
        
        # Weld Speed
        self._create_parameter_input(
            self.continuous_frame,
            "Weld Speed (%):",
            "continuous_speed",
            30,
            "Movement speed during welding"
        )
        
        # Path Delay
        self._create_parameter_input(
            self.continuous_frame,
            "Path Delay (ms):",
            "continuous_delay",
            100,
            "Time between path segments"
        )
        
        # Hide continuous frame initially
        self.continuous_frame.pack_forget()
        
        # ===== STATUS DISPLAY =====
        status_frame = tk.LabelFrame(
            main_frame,
            text="Status",
            font=('Arial', 12, 'bold'),
            bg='#2a2a2a',
            fg='white',
            padx=15,
            pady=15
        )
        status_frame.pack(fill=tk.X, pady=(0, 15))
        
        self.status_label = tk.Label(
            status_frame,
            text="⚪ Ready",
            font=('Arial', 11),
            bg='#2a2a2a',
            fg='white',
            anchor=tk.W
        )
        self.status_label.pack(fill=tk.X)
        
        # ===== CONTROL BUTTONS =====
        button_frame = tk.Frame(main_frame, bg='#1a1a1a')
        button_frame.pack(fill=tk.X, pady=(0, 15))
        
        self.start_button = tk.Button(
            button_frame,
            text="START",
            font=('Arial', 14, 'bold'),
            bg='#00cc00',
            fg='white',
            activebackground='#00ff00',
            command=self.start_welding,
            width=12,
            height=2
        )
        self.start_button.pack(side=tk.LEFT, padx=5)
        
        self.stop_button = tk.Button(
            button_frame,
            text="STOP",
            font=('Arial', 14, 'bold'),
            bg='#cc0000',
            fg='white',
            activebackground='#ff0000',
            command=self.stop_welding,
            width=12,
            height=2,
            state=tk.DISABLED
        )
        self.stop_button.pack(side=tk.LEFT, padx=5)
        
        # ===== EMERGENCY NOTICE =====
        emergency_label = tk.Label(
            main_frame,
            text="⚠ Emergency Stop: Press Ctrl+S",
            font=('Arial', 10, 'italic'),
            bg='#1a1a1a',
            fg='#ffaa00'
        )
        emergency_label.pack(pady=(10, 0))
        
        # ===== INFO PANEL =====
        info_frame = tk.LabelFrame(
            main_frame,
            text="Information",
            font=('Arial', 10),
            bg='#2a2a2a',
            fg='white',
            padx=10,
            pady=10
        )
        info_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
        
        info_text = tk.Text(
            info_frame,
            height=6,
            font=('Courier', 9),
            bg='#1a1a1a',
            fg='#00ff00',
            wrap=tk.WORD,
            state=tk.DISABLED
        )
        info_text.pack(fill=tk.BOTH, expand=True)
        
        self.info_text = info_text
        
        self._update_info_text()
    
    def _create_parameter_input(self, parent, label_text, var_name, default_value, tooltip):
        """Create labeled input field with tooltip."""
        row_frame = tk.Frame(parent, bg='#2a2a2a')
        row_frame.pack(fill=tk.X, pady=5)
        
        label = tk.Label(
            row_frame,
            text=label_text,
            font=('Arial', 10),
            bg='#2a2a2a',
            fg='white',
            width=20,
            anchor=tk.W
        )
        label.pack(side=tk.LEFT, padx=(0, 10))
        
        entry_var = tk.StringVar(value=str(default_value))
        entry = tk.Entry(
            row_frame,
            textvariable=entry_var,
            font=('Arial', 10),
            width=15,
            bg='#3a3a3a',
            fg='white',
            insertbackground='white'
        )
        entry.pack(side=tk.LEFT)
        
        # Store variable reference
        setattr(self, var_name + "_var", entry_var)
        
        # Tooltip
        info_label = tk.Label(
            row_frame,
            text=f"ℹ {tooltip}",
            font=('Arial', 8),
            bg='#2a2a2a',
            fg='#888888',
            anchor=tk.W
        )
        info_label.pack(side=tk.LEFT, padx=(10, 0))
    
    def _on_mode_change(self):
        """Handle welding mode change."""
        mode = self.mode_var.get()
        
        if mode == "spot":
            self.continuous_frame.pack_forget()
            self.spot_frame.pack(fill=tk.X, pady=(0, 15), before=self.continuous_frame)
        else:
            self.spot_frame.pack_forget()
            self.continuous_frame.pack(fill=tk.X, pady=(0, 15))
        
        self._update_info_text()
    
    def _update_info_text(self):
        """Update information panel."""
        mode = self.mode_var.get()
        
        info_lines = [
            "═" * 60,
            f"Mode: {'SPOT WELDING' if mode == 'spot' else 'CONTINUOUS WELDING'}",
            "═" * 60,
        ]
        
        if mode == "spot":
            info_lines.extend([
                "",
                "Spot welding will:",
                "  1. Move to each weld point",
                "  2. Apply weld for specified time",
                "  3. Retract by offset",
                "  4. Move to next point",
                "",
                "All welding commands embedded in motion frames.",
                "ESP32 toggles GPIO 25/26/27 based on WELD:ON/OFF."
            ])
        else:
            info_lines.extend([
                "",
                "Continuous welding will:",
                "  1. Move to start of path",
                "  2. Start welding (WELD:ON)",
                "  3. Follow path continuously",
                "  4. Stop welding (WELD:OFF) at end",
                "",
                "All welding commands embedded in motion frames.",
                "ESP32 toggles GPIO 25/26/27 based on WELD:ON/OFF."
            ])
        
        self.info_text.config(state=tk.NORMAL)
        self.info_text.delete(1.0, tk.END)
        self.info_text.insert(1.0, "\n".join(info_lines))
        self.info_text.config(state=tk.DISABLED)
    
    def start_welding(self):
        """Start welding operation."""
        if self.is_welding_active:
            messagebox.showwarning("Already Running", "Welding operation already in progress")
            return
        
        # Get mode
        mode = self.mode_var.get()
        
        # Configure welding engine
        try:
            if mode == "spot":
                weld_time = float(self.spot_weld_time_var.get())
                spacing = float(self.spot_spacing_var.get())
                retract = float(self.spot_retract_var.get())
                
                self.welding_engine.set_spot_parameters(weld_time, spacing, retract)
                
            else:  # continuous
                speed = float(self.continuous_speed_var.get())
                delay = float(self.continuous_delay_var.get())
                
                self.welding_engine.set_continuous_parameters(speed, delay)
                
        except ValueError as e:
            messagebox.showerror("Invalid Input", f"Please enter valid numeric values:\n{e}")
            return
        
        # Update UI
        self.is_welding_active = True
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        self.status_label.config(text="🔥 Welding Active", fg='#ff6600')
        
        # Start welding in separate thread
        self.weld_thread = threading.Thread(target=self._welding_worker, args=(mode,), daemon=True)
        self.weld_thread.start()
        
        print(f"🔥 Welding started: {mode} mode")
    
    def stop_welding(self):
        """Stop welding operation."""
        if not self.is_welding_active:
            return
        
        self.is_welding_active = False
        
        # Send WELD:OFF command
        self._send_weld_off()
        
        # Update UI
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.status_label.config(text="⚪ Stopped", fg='white')
        
        print("⏹ Welding stopped")
    
    def emergency_stop(self):
        """Emergency stop - immediately turn off welding."""
        print("🚨 EMERGENCY STOP - Welding OFF")
        
        self.is_welding_active = False
        
        # Send emergency stop with WELD:OFF
        emergency_commands = self.welding_engine.generate_emergency_stop_sequence()
        for cmd in emergency_commands:
            self.esp32.send_command(cmd, priority=True)
        
        # Update UI
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.status_label.config(text="🚨 EMERGENCY STOP", fg='#ff0000')
        
        messagebox.showwarning("Emergency Stop", "Welding emergency stop activated!")
    
    def _welding_worker(self, mode):
        """Background worker for welding operations."""
        try:
            if mode == "spot":
                self._execute_spot_welding()
            else:
                self._execute_continuous_welding()
            
            # Finished successfully
            if self.is_welding_active:
                self.window.after(0, self._welding_complete)
                
        except Exception as e:
            print(f"❌ Welding error: {e}")
            self.window.after(0, lambda: messagebox.showerror("Welding Error", str(e)))
            self.window.after(0, self.stop_welding)
    
    def _execute_spot_welding(self):
        """Execute spot welding sequence."""
        # Get current robot positions (simplified - use Teach points in production)
        weld_points = [
            {'J1': 90, 'J2': 120, 'J3': 45},
            {'J1': 100, 'J2': 110, 'J3': 50},
            {'J1': 110, 'J2': 100, 'J3': 55}
        ]
        
        # Generate command sequence
        commands = self.welding_engine.generate_spot_weld_sequence(weld_points)
        
        # Send commands through motion queue
        for cmd in commands:
            if not self.is_welding_active:
                break
            self.esp32.send_command(cmd)
    
    def _execute_continuous_welding(self):
        """Execute continuous welding sequence."""
        # Get path points (simplified - use Teach path in production)
        start_point = {'J1': 90, 'J2': 120, 'J3': 45}
        end_point = {'J1': 120, 'J2': 90, 'J3': 60}
        
        path_points = self.welding_engine.interpolate_path_points(start_point, end_point, num_points=20)
        
        # Generate command sequence
        commands = self.welding_engine.generate_continuous_weld_sequence(path_points)
        
        # Send commands through motion queue
        for cmd in commands:
            if not self.is_welding_active:
                break
            self.esp32.send_command(cmd)
    
    def _send_weld_off(self):
        """Send WELD:OFF command."""
        from ..robot.command_builder import generate_move_command
        cmd = generate_move_command(self.robot, speed=0, time_ms=50, weld_state="OFF")
        self.esp32.send_command(cmd, priority=True)
    
    def _welding_complete(self):
        """Called when welding completes successfully."""
        self.is_welding_active = False
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.status_label.config(text="✅ Complete", fg='#00ff00')
        
        messagebox.showinfo("Complete", "Welding operation completed successfully!")


# Testing
if __name__ == "__main__":
    print("Welding Window Test")
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
    
    root = tk.Tk()
    root.withdraw()
    
    robot = MockRobot()
    window = WeldingWindow(root, robot)
    
    root.mainloop()
