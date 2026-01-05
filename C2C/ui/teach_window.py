"""Teach Window - Industrial teach pendant interface"""

import tkinter as tk
from tkinter import messagebox
import time
import threading

# Import command generation modules
try:
    from ..robot.command_builder import generate_move_command, generate_stop_command, format_command_for_display
    from ..hardware.esp32_comm import send_command_to_esp32
except ImportError:
    try:
        from C2C.robot.command_builder import generate_move_command, generate_stop_command, format_command_for_display
        from C2C.hardware.esp32_comm import send_command_to_esp32
    except ImportError:
        from robot.command_builder import generate_move_command, generate_stop_command, format_command_for_display
        from hardware.esp32_comm import send_command_to_esp32


class TeachWindow:
    def __init__(self, parent, robot_model, update_callback):
        self.robot = robot_model
        self.update_callback = update_callback
        self.is_teaching = False
        self.is_repeating = False
        self.teach_data = []  # List of (timestamp, angles_dict)
        self.teach_start_time = None
        
        # Command logging
        self.command_log_text = None  # Will be set in _create_widgets
        
        # Create window
        self.window = tk.Toplevel(parent)
        self.window.title("Teach View")
        self.window.geometry("1400x800")
        self.window.configure(bg='#1a1a1a')
        
        # Make it stay on top but not modal
        self.window.transient(parent)
        
        # Bind emergency stop
        self.window.bind('<Control-s>', lambda e: self.emergency_stop())
        
        self._create_widgets()
        self._update_sliders()
        
    def _create_widgets(self):
        """Create the teach interface layout"""
        main_container = tk.Frame(self.window, bg='#1a1a1a')
        main_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # ===== LEFT PANEL: SLIDERS =====
        left_panel = tk.Frame(main_container, bg='#2a2a2a', width=400)
        left_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 5))
        left_panel.pack_propagate(False)
        
        slider_title = tk.Label(left_panel, text="Joint Sliders", 
                               bg='#2a2a2a', fg='white',
                               font=('Arial', 14, 'bold'))
        slider_title.pack(pady=10)
        
        # Scrollable slider canvas
        canvas_frame = tk.Frame(left_panel, bg='#2a2a2a')
        canvas_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.slider_canvas = tk.Canvas(canvas_frame, bg='#2a2a2a', 
                                      highlightthickness=0)
        scrollbar = tk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL, 
                               command=self.slider_canvas.xview)
        self.slider_canvas.configure(xscrollcommand=scrollbar.set)
        
        scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
        self.slider_canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        
        self.slider_frame = tk.Frame(self.slider_canvas, bg='#2a2a2a')
        self.canvas_window = self.slider_canvas.create_window(
            (0, 0), window=self.slider_frame, anchor='nw')
        
        self.slider_frame.bind('<Configure>', 
            lambda e: self.slider_canvas.configure(
                scrollregion=self.slider_canvas.bbox('all')))
        
        self.sliders = []
        
        # ===== CENTER PANEL: GRAPH =====
        center_panel = tk.Frame(main_container, bg='white', relief=tk.RAISED, bd=2)
        center_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        
        # Graph header
        graph_header = tk.Frame(center_panel, bg='white')
        graph_header.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)
        
        graph_title = tk.Label(graph_header, text="3D Graph", 
                              font=('Arial', 14, 'bold'), bg='white')
        graph_title.pack(side=tk.LEFT)
        
        # View mode selection
        self.view_mode = tk.StringVar(value="3D")
        mode_3d = tk.Radiobutton(graph_header, text="3D", 
                                variable=self.view_mode, value="3D",
                                command=self._update_view_mode, 
                                bg='white', font=('Arial', 10))
        mode_3d.pack(side=tk.RIGHT, padx=5)
        mode_2d = tk.Radiobutton(graph_header, text="2D", 
                                variable=self.view_mode, value="2D",
                                command=self._update_view_mode, 
                                bg='white', font=('Arial', 10))
        mode_2d.pack(side=tk.RIGHT, padx=5)
        
        # Graph canvas container
        self.graph_frame = tk.Frame(center_panel, bg='white')
        self.graph_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Import and create graph views
        try:
            from .robot_view_3d import RobotView3D
            from .robot_view_2d import RobotView2D
        except ImportError:
            try:
                from C2C.ui.robot_view_3d import RobotView3D
                from C2C.ui.robot_view_2d import RobotView2D
            except ImportError:
                from ui.robot_view_3d import RobotView3D
                from ui.robot_view_2d import RobotView2D
        
        self.view_3d = RobotView3D(self.graph_frame)
        self.view_2d = RobotView2D(self.graph_frame)
        
        # Coordinate display at bottom
        coord_frame = tk.Frame(center_panel, bg='white')
        coord_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=5, pady=5)
        
        self.coord_label = tk.Label(coord_frame, 
                                    text="X: 0.00   Y: 0.00   Z: 0.00",
                                    bg='#1a1a1a', fg='#00ff00',
                                    font=('Arial', 12, 'bold'),
                                    relief=tk.SUNKEN, bd=2, pady=5)
        self.coord_label.pack(fill=tk.X)
        
        # ===== RIGHT PANEL: CONTROLS =====
        right_panel = tk.Frame(main_container, bg='#2a2a2a', width=300)
        right_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(5, 0))
        right_panel.pack_propagate(False)
        
        control_title = tk.Label(right_panel, text="Controls", 
                                bg='#2a2a2a', fg='white',
                                font=('Arial', 14, 'bold'))
        control_title.pack(pady=10)
        
        # --- TEACH CONTROL ---
        teach_frame = tk.LabelFrame(right_panel, text="Teach Control", 
                                   bg='#2a2a2a', fg='white',
                                   font=('Arial', 11, 'bold'), 
                                   padx=10, pady=10)
        teach_frame.pack(fill=tk.X, padx=10, pady=10)
        
        self.start_teach_btn = tk.Button(teach_frame, text="Start Teach", 
                                        bg='#006400', fg='white',
                                        font=('Arial', 12, 'bold'),
                                        height=2, command=self._start_teach)
        self.start_teach_btn.pack(fill=tk.X, pady=5)
        
        self.stop_teach_btn = tk.Button(teach_frame, text="Stop Teach", 
                                       bg='#8B0000', fg='white',
                                       font=('Arial', 12, 'bold'),
                                       height=2, command=self._stop_teach,
                                       state=tk.DISABLED)
        self.stop_teach_btn.pack(fill=tk.X, pady=5)
        
        self.teach_status_label = tk.Label(teach_frame, 
                                          text="Status: Idle", 
                                          bg='#2a2a2a', fg='#888888',
                                          font=('Arial', 9))
        self.teach_status_label.pack(pady=5)
        
        # --- REPEAT CONTROL ---
        repeat_frame = tk.LabelFrame(right_panel, text="Repeat Control", 
                                    bg='#2a2a2a', fg='white',
                                    font=('Arial', 11, 'bold'), 
                                    padx=10, pady=10)
        repeat_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # Cycle option
        cycle_option_frame = tk.Frame(repeat_frame, bg='#2a2a2a')
        cycle_option_frame.pack(fill=tk.X, pady=5)
        
        self.repeat_mode = tk.StringVar(value="cycle")
        cycle_radio = tk.Radiobutton(cycle_option_frame, text="Cycle", 
                                    variable=self.repeat_mode, value="cycle",
                                    bg='#2a2a2a', fg='white',
                                    selectcolor='#3a3a3a',
                                    font=('Arial', 10),
                                    command=self._on_repeat_mode_change)
        cycle_radio.pack(side=tk.LEFT)
        
        self.cycle_entry = tk.Entry(cycle_option_frame, 
                                   bg='#3a3a3a', fg='white',
                                   font=('Arial', 10), width=5,
                                   insertbackground='white')
        self.cycle_entry.insert(0, "5")
        self.cycle_entry.pack(side=tk.LEFT, padx=10)
        
        cycle_label = tk.Label(cycle_option_frame, text="times", 
                             bg='#2a2a2a', fg='white',
                             font=('Arial', 10))
        cycle_label.pack(side=tk.LEFT)
        
        # Continuous option
        continuous_radio = tk.Radiobutton(repeat_frame, 
                                         text="Continuous Repeat", 
                                         variable=self.repeat_mode, 
                                         value="continuous",
                                         bg='#2a2a2a', fg='white',
                                         selectcolor='#3a3a3a',
                                         font=('Arial', 10),
                                         command=self._on_repeat_mode_change)
        continuous_radio.pack(anchor=tk.W, pady=5)
        
        # Repeat buttons
        self.repeat_teach_btn = tk.Button(repeat_frame, 
                                         text="Repeat Teach", 
                                         bg='#006400', fg='white',
                                         font=('Arial', 12, 'bold'),
                                         height=2, 
                                         command=self._repeat_teach)
        self.repeat_teach_btn.pack(fill=tk.X, pady=5)
        
        self.stop_repeat_btn = tk.Button(repeat_frame, 
                                        text="Stop Repeat", 
                                        bg='#8B0000', fg='white',
                                        font=('Arial', 12, 'bold'),
                                        height=2, 
                                        command=self._stop_repeat,
                                        state=tk.DISABLED)
        self.stop_repeat_btn.pack(fill=tk.X, pady=5)
        
        self.repeat_status_label = tk.Label(repeat_frame, 
                                           text="Status: Idle", 
                                           bg='#2a2a2a', fg='#888888',
                                           font=('Arial', 9))
        self.repeat_status_label.pack(pady=5)
        
        # --- EMERGENCY STOP ---
        emergency_frame = tk.Frame(right_panel, bg='#2a2a2a')
        emergency_frame.pack(fill=tk.X, padx=10, pady=20)
        
        emergency_btn = tk.Button(emergency_frame, 
                                 text="EMERGENCY\n(Ctrl+S)", 
                                 bg='#8B0000', fg='white',
                                 font=('Arial', 14, 'bold'),
                                 height=3, 
                                 command=self.emergency_stop)
        emergency_btn.pack(fill=tk.X)
        
    def _update_sliders(self):
        """Rebuild sliders for all joints"""
        for widget in self.slider_frame.winfo_children():
            widget.destroy()
        self.sliders.clear()
        
        for i, link in enumerate(self.robot.links):
            slider_col = tk.Frame(self.slider_frame, bg='#1a1a1a', 
                                relief=tk.RAISED, bd=2)
            slider_col.pack(side=tk.LEFT, padx=5, pady=5)
            
            # Joint header
            joint_label = tk.Label(slider_col, text=f"Joint {i+1}", 
                                  bg='#1a1a1a', fg='white',
                                  font=('Arial', 10, 'bold'))
            joint_label.pack(pady=5)
            
            # Motor info
            motor_info = tk.Label(slider_col, 
                                text=f"{link.motor_type.capitalize()}\n"
                                     f"{link.rotation_axis}-axis", 
                                bg='#1a1a1a', fg='#888888',
                                font=('Arial', 8))
            motor_info.pack()
            
            # Vertical slider
            slider = tk.Scale(slider_col, 
                            from_=link.max_angle, to=link.min_angle,
                            orient=tk.VERTICAL, bg='#2a2a2a', 
                            fg='#00ff00',
                            troughcolor='#0a0a0a', 
                            activebackground='#3a3a3a',
                            length=400, width=30, sliderlength=40,
                            showvalue=0,
                            command=lambda v, idx=i: self._on_slider_change(idx, v))
            slider.set(link.angle)
            slider.pack(pady=5)
            
            # Numeric input
            entry = tk.Entry(slider_col, bg='#2a2a2a', fg='#00ff00',
                           font=('Arial', 11), width=8, 
                           justify=tk.CENTER,
                           insertbackground='#00ff00',
                           relief=tk.SUNKEN, bd=2)
            entry.insert(0, f"{link.angle:.1f}")
            entry.pack(pady=5)
            
            # Bind entry events
            entry.bind('<Return>', 
                      lambda e, idx=i, s=slider, ent=entry: 
                      self._on_entry_change(idx, s, ent))
            entry.bind('<FocusOut>', 
                      lambda e, idx=i, s=slider, ent=entry: 
                      self._on_entry_change(idx, s, ent))
            
            self.sliders.append({'slider': slider, 'entry': entry})
        
        # Update view
        self._update_graph()
    
    def _on_slider_change(self, index, value):
        """Handle slider movement"""
        if index < len(self.robot.links):
            self.robot.links[index].angle = float(value)
            
            # Update entry
            if index < len(self.sliders):
                self.sliders[index]['entry'].delete(0, tk.END)
                self.sliders[index]['entry'].insert(0, f"{float(value):.1f}")
            
            # Generate and send command to ESP32
            command = generate_move_command(self.robot, speed=30, time_ms=100)
            if command:
                send_command_to_esp32(command)
                print(f"📤 Command generated:")
                print(format_command_for_display(command))
            
            # Record if teaching
            if self.is_teaching:
                self._record_position()
            
            self._update_graph()
    
    def _on_entry_change(self, index, slider, entry):
        """Handle manual entry"""
        try:
            value = float(entry.get())
            if index < len(self.robot.links):
                link = self.robot.links[index]
                value = max(link.min_angle, min(link.max_angle, value))
                self.robot.links[index].angle = value
                slider.set(value)
                entry.delete(0, tk.END)
                entry.insert(0, f"{value:.1f}")
                
                # Record if teaching
                if self.is_teaching:
                    self._record_position()
                
                self._update_graph()
        except ValueError:
            if index < len(self.robot.links):
                entry.delete(0, tk.END)
                entry.insert(0, f"{self.robot.links[index].angle:.1f}")
    
    def _update_graph(self):
        """Update the graph visualization"""
        points = self.robot.get_points()
        
        if self.view_mode.get() == "3D":
            self.view_2d.canvas.get_tk_widget().pack_forget()
            self.view_3d.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
            self.view_3d.update(points)
        else:
            self.view_3d.canvas.get_tk_widget().pack_forget()
            self.view_2d.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
            self.view_2d.update(points)
        
        # Update coordinates
        x, y, z = self.robot.get_tool_position()
        self.coord_label.config(text=f"X: {x:.2f}   Y: {y:.2f}   Z: {z:.2f}")
        
        # Callback to main window
        if self.update_callback:
            self.update_callback()
    
    def _update_view_mode(self):
        """Switch between 2D and 3D view"""
        self._update_graph()
    
    def _on_repeat_mode_change(self):
        """Handle repeat mode change"""
        pass
    
    # ===== TEACH CONTROL METHODS =====
    
    def _start_teach(self):
        """Start teaching mode"""
        self.is_teaching = True
        self.teach_data = []
        self.teach_start_time = time.time()
        
        # Record initial position
        self._record_position()
        
        # Update UI
        self.start_teach_btn.config(state=tk.DISABLED)
        self.stop_teach_btn.config(state=tk.NORMAL)
        self.teach_status_label.config(text="Status: Recording...", fg='#00ff00')
        
        print("▶ Teach started - Recording motion...")
    
    def _stop_teach(self):
        """Stop teaching mode"""
        self.is_teaching = False
        
        # Update UI
        self.start_teach_btn.config(state=tk.NORMAL)
        self.stop_teach_btn.config(state=tk.DISABLED)
        self.teach_status_label.config(
            text=f"Status: Recorded {len(self.teach_data)} points", 
            fg='#888888')
        
        print(f"⏹ Teach stopped - {len(self.teach_data)} positions recorded")
    
    def _record_position(self):
        """Record current joint angles with timestamp"""
        if not self.is_teaching:
            return
        
        elapsed_time = time.time() - self.teach_start_time
        angles = {i: link.angle for i, link in enumerate(self.robot.links)}
        self.teach_data.append((elapsed_time, angles))
    
    # ===== REPEAT CONTROL METHODS =====
    
    def _repeat_teach(self):
        """Start repeating recorded motion"""
        if not self.teach_data:
            messagebox.showwarning("No Data", 
                                 "No teach data to repeat. Please teach first.",
                                 parent=self.window)
            return
        
        try:
            if self.repeat_mode.get() == "cycle":
                cycles = int(self.cycle_entry.get())
                if cycles <= 0:
                    raise ValueError
            else:
                cycles = -1  # Infinite
        except ValueError:
            messagebox.showerror("Invalid Input", 
                               "Please enter a valid cycle count",
                               parent=self.window)
            return
        
        self.is_repeating = True
        
        # Update UI
        self.repeat_teach_btn.config(state=tk.DISABLED)
        self.stop_repeat_btn.config(state=tk.NORMAL)
        self.start_teach_btn.config(state=tk.DISABLED)
        self.repeat_status_label.config(text="Status: Repeating...", fg='#00ff00')
        
        # Start repeat thread
        thread = threading.Thread(target=self._repeat_worker, args=(cycles,), 
                                 daemon=True)
        thread.start()
    
    def _repeat_worker(self, cycles):
        """Worker thread for repeating motion"""
        cycle_count = 0
        
        while self.is_repeating and (cycles < 0 or cycle_count < cycles):
            cycle_count += 1
            
            # Update status
            if cycles < 0:
                status_text = f"Status: Repeating... (Cycle {cycle_count})"
            else:
                status_text = f"Status: Repeating... ({cycle_count}/{cycles})"
            
            self.window.after(0, lambda t=status_text: 
                            self.repeat_status_label.config(text=t))
            
            # Play through teach data
            start_time = time.time()
            for timestamp, angles in self.teach_data:
                if not self.is_repeating:
                    break
                
                # Wait for correct time
                target_time = start_time + timestamp
                wait_time = target_time - time.time()
                if wait_time > 0:
                    time.sleep(wait_time)
                
                # Set angles
                for joint_idx, angle in angles.items():
                    if joint_idx < len(self.robot.links):
                        self.robot.links[joint_idx].angle = angle
                
                # Generate and send command to ESP32
                command = generate_move_command(self.robot, speed=30, time_ms=100)
                if command:
                    send_command_to_esp32(command)
                    print(f"📤 Repeat Command:")
                    print(format_command_for_display(command))
                
                # Update UI
                self.window.after(0, self._sync_sliders_from_robot)
                self.window.after(0, self._update_graph)
        
        # Finished
        self.window.after(0, self._repeat_finished)
    
    def _stop_repeat(self):
        """Stop repeating motion"""
        self.is_repeating = False
    
    def _repeat_finished(self):
        """Called when repeat is finished"""
        self.is_repeating = False
        
        # Update UI
        self.repeat_teach_btn.config(state=tk.NORMAL)
        self.stop_repeat_btn.config(state=tk.DISABLED)
        self.start_teach_btn.config(state=tk.NORMAL)
        self.repeat_status_label.config(text="Status: Finished", fg='#888888')
        
        print("✓ Repeat finished")
    
    def _sync_sliders_from_robot(self):
        """Sync slider positions from robot model"""
        for i, link in enumerate(self.robot.links):
            if i < len(self.sliders):
                self.sliders[i]['slider'].set(link.angle)
                self.sliders[i]['entry'].delete(0, tk.END)
                self.sliders[i]['entry'].insert(0, f"{link.angle:.1f}")
    
    # ===== EMERGENCY STOP =====
    
    def emergency_stop(self):
        """Emergency stop all operations"""
        print("🚨 EMERGENCY STOP 🚨")
        
        # Send STOP command to ESP32 immediately (priority)
        stop_command = generate_stop_command()
        send_command_to_esp32(stop_command, priority=True)
        print(f"📤 EMERGENCY STOP Command sent: {stop_command}")
        
        # Stop all operations
        self.is_teaching = False
        self.is_repeating = False
        
        # Reset robot to safe position
        for link in self.robot.links:
            if link.motor_type == "servo":
                link.angle = (link.min_angle + link.max_angle) / 2
            else:
                link.angle = 0
        
        # Send reset position command
        reset_command = generate_move_command(self.robot, speed=50, time_ms=500)
        if reset_command:
            send_command_to_esp32(reset_command)
            print("📤 Reset position command sent")
        
        # Update UI
        self.start_teach_btn.config(state=tk.NORMAL)
        self.stop_teach_btn.config(state=tk.DISABLED)
        self.teach_status_label.config(text="Status: Emergency Stop", fg='#FF0000')
        
        self.repeat_teach_btn.config(state=tk.NORMAL)
        self.stop_repeat_btn.config(state=tk.DISABLED)
        self.repeat_status_label.config(text="Status: Emergency Stop", fg='#FF0000')
        
        # Sync and update
        self._sync_sliders_from_robot()
        self._update_graph()
        
        messagebox.showwarning("Emergency Stop", 
                             "All operations stopped!\nRobot reset to safe position.",
                             parent=self.window)
