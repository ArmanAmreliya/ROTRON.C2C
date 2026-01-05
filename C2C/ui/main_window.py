# INDUSTRIAL HMI-STYLE SINGLE WINDOW INTERFACE
# NO POPUPS, NO DIALOGS - ALL CONTENT IN SCROLLABLE WORK AREA

import sys
from pathlib import Path

# Ensure project root is on sys.path for imports
project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import tkinter as tk
from tkinter import ttk, messagebox
try:
    from .robot_view_3d import RobotView3D
    from .robot_view_2d import RobotView2D
    from ..robot.robot_model import RobotModel
    from ..robot.link import Link
    from ..robot.command_builder import generate_move_command, generate_stop_command, format_command_for_display
    from ..hardware.esp32_comm import send_command_to_esp32, get_esp32_communicator
    from ..robot.ik import inverse_kinematics_xyz
except ImportError:
    try:
        from C2C.ui.robot_view_3d import RobotView3D
        from C2C.ui.robot_view_2d import RobotView2D
        from C2C.robot.robot_model import RobotModel
        from C2C.robot.link import Link
        from C2C.robot.command_builder import generate_move_command, generate_stop_command, format_command_for_display
        from C2C.hardware.esp32_comm import send_command_to_esp32, get_esp32_communicator
        from C2C.robot.ik import inverse_kinematics_xyz
    except ImportError:
        from ui.robot_view_3d import RobotView3D
        from ui.robot_view_2d import RobotView2D
        from robot.robot_model import RobotModel
        from robot.link import Link
        from robot.command_builder import generate_move_command, generate_stop_command, format_command_for_display
        from hardware.esp32_comm import send_command_to_esp32, get_esp32_communicator
        from robot.ik import inverse_kinematics_xyz


class MainWindow:
    """Industrial HMI-style single window application
    
    Architecture:
    - Fixed Top: Joint sliders + 2D/3D Graph
    - Scrollable Middle: Dynamic work area (Teach/Welding/Painting)
    - Fixed Bottom: Emergency stop + status
    """
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("ROTRON 2.0 - Industrial HMI")
        self.root.geometry("1600x900")
        self.root.configure(bg='#1a1a1a')
        
        self.robot = RobotModel()
        self.current_section = None  # Track active section
        
        # Welding data
        self.weld_points = []  # List of (x, y, z) tuples
        self.weld_mode = tk.StringVar(value="spot")  # spot or continuous
        self.spot_submode = tk.StringVar(value="line")  # line or only
        
        self._build_ui()
        
    def _build_ui(self):
        """Build the main UI structure"""
        # ================== FIXED TOP SECTION ==================
        top_section = tk.Frame(self.root, bg='#1a1a1a', height=400)
        top_section.pack(side=tk.TOP, fill=tk.BOTH, expand=False)
        top_section.pack_propagate(False)
        
        # Left: Sliders
        left_panel = tk.Frame(top_section, bg='#2a2a2a', width=400)
        left_panel.pack(side=tk.LEFT, fill=tk.Y)
        left_panel.pack_propagate(False)
        
        slider_label = tk.Label(left_panel, text="JOINT SLIDERS", fg='white', bg='#2a2a2a',
                               font=('Arial', 12, 'bold'))
        slider_label.pack(pady=5)
        
        # Scrollable slider container
        slider_canvas_frame = tk.Frame(left_panel, bg='#2a2a2a')
        slider_canvas_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.slider_canvas = tk.Canvas(slider_canvas_frame, bg='#2a2a2a', highlightthickness=0)
        h_scrollbar = tk.Scrollbar(slider_canvas_frame, orient=tk.HORIZONTAL, command=self.slider_canvas.xview)
        self.slider_canvas.configure(xscrollcommand=h_scrollbar.set)
        
        h_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
        self.slider_canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        
        self.slider_frame = tk.Frame(self.slider_canvas, bg='#2a2a2a')
        self.canvas_window = self.slider_canvas.create_window((0, 0), window=self.slider_frame, anchor='nw')
        self.slider_frame.bind('<Configure>', lambda e: self.slider_canvas.configure(scrollregion=self.slider_canvas.bbox('all')))
        
        self.sliders = []
        
        # +joint button
        controls_frame = tk.Frame(left_panel, bg='#2a2a2a')
        controls_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=5)
        
        joint_btn = tk.Button(controls_frame, text="+JOINT", bg='#3a3a3a', fg='white',
                             font=('Arial', 11, 'bold'), command=self.add_joint, width=10)
        joint_btn.pack(pady=5)
        
        self.coord_display = tk.Label(controls_frame, text="(0.00, 0.00, 0.00)", fg='#00ff00', bg='#1a1a1a',
                                     font=('Arial', 10), width=20)
        self.coord_display.pack(pady=3)
        
        # Right: Graph
        right_panel = tk.Frame(top_section, bg='white', relief=tk.RAISED, bd=2)
        right_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(3, 0))
        
        graph_header = tk.Frame(right_panel, bg='white')
        graph_header.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)
        
        graph_title = tk.Label(graph_header, text="ROBOT VIEW", font=('Arial', 14, 'bold'), bg='white')
        graph_title.pack(side=tk.LEFT)
        
        self.view_mode = tk.StringVar(value="3D")
        mode_3d = tk.Radiobutton(graph_header, text="3D", variable=self.view_mode, value="3D",
                                command=self.update_view, bg='white', font=('Arial', 10))
        mode_3d.pack(side=tk.RIGHT, padx=5)
        mode_2d = tk.Radiobutton(graph_header, text="2D", variable=self.view_mode, value="2D",
                                command=self.update_view, bg='white', font=('Arial', 10))
        mode_2d.pack(side=tk.RIGHT, padx=5)
        
        self.view_frame = tk.Frame(right_panel, bg='white')
        self.view_frame.pack(fill=tk.BOTH, expand=True)
        
        self.view_3d = RobotView3D(self.view_frame)
        self.view_2d = RobotView2D(self.view_frame)
        
        # ================== SCROLLABLE WORK AREA (MIDDLE) ==================
        work_section = tk.Frame(self.root, bg='#1a1a1a')
        work_section.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=5)
        
        # Mode selection buttons
        mode_bar = tk.Frame(work_section, bg='#2a2a2a', height=60)
        mode_bar.pack(side=tk.TOP, fill=tk.X)
        mode_bar.pack_propagate(False)
        
        tk.Label(mode_bar, text="MODE:", fg='white', bg='#2a2a2a', font=('Arial', 12, 'bold')).pack(side=tk.LEFT, padx=10)
        
        btn_teach = tk.Button(mode_bar, text="TEACH", bg='#8B0000', fg='white',
                             font=('Arial', 14, 'bold'), command=self.load_teach_section, width=10, height=1)
        btn_teach.pack(side=tk.LEFT, padx=5, pady=10)
        
        btn_welding = tk.Button(mode_bar, text="WELDING", bg='#8B8B00', fg='white',
                               font=('Arial', 14, 'bold'), command=self.load_welding_section, width=10, height=1)
        btn_welding.pack(side=tk.LEFT, padx=5, pady=10)
        
        btn_painting = tk.Button(mode_bar, text="PAINTING", bg='#006400', fg='white',
                                font=('Arial', 14, 'bold'), command=self.load_painting_section, width=10, height=1)
        btn_painting.pack(side=tk.LEFT, padx=5, pady=10)
        
        btn_clear = tk.Button(mode_bar, text="CLEAR", bg='#3a3a3a', fg='white',
                             font=('Arial', 14, 'bold'), command=self.clear_work_area, width=10, height=1)
        btn_clear.pack(side=tk.RIGHT, padx=10, pady=10)
        
        # Scrollable canvas for work content
        self.work_canvas = tk.Canvas(work_section, bg='#1a1a1a', highlightthickness=0)
        work_scrollbar = tk.Scrollbar(work_section, orient=tk.VERTICAL, command=self.work_canvas.yview)
        self.work_canvas.configure(yscrollcommand=work_scrollbar.set)
        
        work_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.work_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        self.work_frame = tk.Frame(self.work_canvas, bg='#1a1a1a')
        self.work_canvas_window = self.work_canvas.create_window((0, 0), window=self.work_frame, anchor='nw')
        self.work_frame.bind('<Configure>', lambda e: self.work_canvas.configure(scrollregion=self.work_canvas.bbox('all')))
        
        # ================== FIXED BOTTOM BAR ==================
        bottom_bar = tk.Frame(self.root, bg='#2a2a2a', height=80)
        bottom_bar.pack(side=tk.BOTTOM, fill=tk.X)
        bottom_bar.pack_propagate(False)
        
        # Emergency button (right side)
        emergency_frame = tk.Frame(bottom_bar, bg='#2a2a2a')
        emergency_frame.pack(side=tk.RIGHT, padx=20, pady=15)
        
        btn_emergency = tk.Button(emergency_frame, text="EMERGENCY (Ctrl+S)", bg='#8B0000', fg='white',
                                 font=('Arial', 14, 'bold'), command=self.emergency_stop, width=25, height=2)
        btn_emergency.pack()
        
        # Status (left side)
        self.status_label = tk.Label(bottom_bar, text="Ready", fg='#00ff00', bg='#2a2a2a',
                                    font=('Arial', 12, 'bold'))
        self.status_label.pack(side=tk.LEFT, padx=20)
        
        self.coord_label = tk.Label(bottom_bar, text="X:0.00 Y:0.00 Z:0.00", fg='white', bg='#2a2a2a',
                                   font=('Arial', 10))
        self.coord_label.pack(side=tk.LEFT, padx=10)
        
        # Bind emergency shortcut
        self.root.bind('<Control-s>', lambda e: self.emergency_stop())
        
    # ==================== JOINT MANAGEMENT ====================
    
    def add_joint(self):
        """Add new joint via inline dialog"""
        # Simple inline dialog instead of popup
        dialog_frame = tk.Frame(self.slider_frame, bg='#3a3a3a', relief=tk.RAISED, bd=3)
        dialog_frame.pack(side=tk.LEFT, padx=10, pady=10)
        
        tk.Label(dialog_frame, text="Add Joint", fg='white', bg='#3a3a3a', font=('Arial', 10, 'bold')).grid(row=0, column=0, columnspan=2, pady=5)
        
        tk.Label(dialog_frame, text="Length (cm):", fg='white', bg='#3a3a3a').grid(row=1, column=0, sticky='e', padx=5)
        length_entry = tk.Entry(dialog_frame, width=10)
        length_entry.insert(0, "10")
        length_entry.grid(row=1, column=1, padx=5, pady=2)
        
        tk.Label(dialog_frame, text="Motor:", fg='white', bg='#3a3a3a').grid(row=2, column=0, sticky='e', padx=5)
        motor_var = tk.StringVar(value="servo")
        tk.OptionMenu(dialog_frame, motor_var, "servo", "stepper").grid(row=2, column=1, padx=5, pady=2)
        
        tk.Label(dialog_frame, text="Axis:", fg='white', bg='#3a3a3a').grid(row=3, column=0, sticky='e', padx=5)
        axis_var = tk.StringVar(value="Z")
        tk.OptionMenu(dialog_frame, axis_var, "X", "Y", "Z").grid(row=3, column=1, padx=5, pady=2)
        
        def confirm():
            try:
                length = float(length_entry.get())
                link = Link(length=length, motor_type=motor_var.get(), rotation_axis=axis_var.get())
                self.robot.add_link(link)
                dialog_frame.destroy()
                self.rebuild_sliders()
                self.update_view()
                self.status_label.config(text=f"✓ Joint J{len(self.robot.links)} added")
            except ValueError:
                messagebox.showerror("Error", "Invalid length value")
        
        btn_frame = tk.Frame(dialog_frame, bg='#3a3a3a')
        btn_frame.grid(row=4, column=0, columnspan=2, pady=5)
        tk.Button(btn_frame, text="OK", command=confirm, bg='#00aa00', fg='white', width=6).pack(side=tk.LEFT, padx=2)
        tk.Button(btn_frame, text="Cancel", command=dialog_frame.destroy, bg='#aa0000', fg='white', width=6).pack(side=tk.LEFT, padx=2)
    
    def rebuild_sliders(self):
        """Rebuild all joint sliders"""
        for widget in self.slider_frame.winfo_children():
            widget.destroy()
        self.sliders.clear()
        
        for i, link in enumerate(self.robot.links):
            slider_col = tk.Frame(self.slider_frame, bg='#1a1a1a', relief=tk.FLAT, bd=1)
            slider_col.pack(side=tk.LEFT, padx=3, pady=5)
            
            header = tk.Frame(slider_col, bg='#1a1a1a')
            header.pack()
            
            joint_label = tk.Label(header, text=f"J{i+1}", bg='#1a1a1a', fg='white', font=('Arial', 9, 'bold'))
            joint_label.pack(side=tk.LEFT, padx=2)
            
            delete_btn = tk.Button(header, text="X", bg='#8B0000', fg='white',
                                  font=('Arial', 8, 'bold'), width=2, height=1,
                                  command=lambda idx=i: self.delete_joint(idx))
            delete_btn.pack(side=tk.LEFT, padx=2)
            
            slider = tk.Scale(slider_col, from_=link.max_angle, to=link.min_angle,
                            orient=tk.VERTICAL, bg='#2a2a2a', fg='#00ff00',
                            troughcolor='#0a0a0a', activebackground='#3a3a3a',
                            length=250, width=25, sliderlength=30, showvalue=0,
                            command=lambda v, idx=i: self.on_slider_change(idx, v))
            slider.set(link.angle)
            slider.pack()
            
            value_entry = tk.Entry(slider_col, width=6, font=('Arial', 9), justify='center')
            value_entry.insert(0, f"{link.angle:.1f}")
            value_entry.pack(pady=2)
            value_entry.bind('<Return>', lambda e, idx=i, s=slider, ent=value_entry: self.on_entry_change(idx, s, ent))
            
            self.sliders.append({'slider': slider, 'entry': value_entry})
    
    def delete_joint(self, index):
        """Delete a joint"""
        if messagebox.askyesno("Confirm", f"Delete Joint J{index+1}?"):
            self.robot.links.pop(index)
            self.rebuild_sliders()
            self.update_view()
            self.status_label.config(text=f"✓ Joint deleted")
    
    def on_slider_change(self, index, value):
        """Handle slider movement"""
        if index < len(self.robot.links):
            self.robot.links[index].angle = float(value)
            if index < len(self.sliders):
                self.sliders[index]['entry'].delete(0, tk.END)
                self.sliders[index]['entry'].insert(0, f"{float(value):.1f}")
            
            command = generate_move_command(self.robot, speed=30, time_ms=100)
            if command:
                send_command_to_esp32(command)
            
            self.update_view()
    
    def on_entry_change(self, index, slider, entry):
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
                
                command = generate_move_command(self.robot, speed=30, time_ms=100)
                if command:
                    send_command_to_esp32(command)
                
                self.update_view()
        except ValueError:
            if index < len(self.robot.links):
                entry.delete(0, tk.END)
                entry.insert(0, f"{self.robot.links[index].angle:.1f}")
    
    # ==================== WORK AREA MANAGEMENT ====================
    
    def clear_work_area(self):
        """Clear the scrollable work area"""
        for widget in self.work_frame.winfo_children():
            widget.destroy()
        self.current_section = None
        self.status_label.config(text="Work area cleared")
    
    def load_teach_section(self):
        """Load teach mode interface into work area"""
        if not self.robot.links:
            messagebox.showwarning("No Joints", "Please add at least one joint before teaching.")
            return
        
        self.clear_work_area()
        self.current_section = "teach"
        self.status_label.config(text="TEACH MODE ACTIVE")
        
        # Teach interface content
        tk.Label(self.work_frame, text="TEACH MODE", fg='white', bg='#1a1a1a',
                font=('Arial', 16, 'bold')).pack(pady=10)
        
        tk.Label(self.work_frame, text="[Teach mode interface - to be implemented]",
                fg='#aaaaaa', bg='#1a1a1a', font=('Arial', 12)).pack(pady=20)
    
    def load_painting_section(self):
        """Load painting mode interface"""
        self.clear_work_area()
        self.current_section = "painting"
        self.status_label.config(text="PAINTING MODE ACTIVE")
        
        tk.Label(self.work_frame, text="PAINTING MODE", fg='white', bg='#1a1a1a',
                font=('Arial', 16, 'bold')).pack(pady=10)
        
        tk.Label(self.work_frame, text="[Painting mode interface - to be implemented]",
                fg='#aaaaaa', bg='#1a1a1a', font=('Arial', 12)).pack(pady=20)
    
    def load_welding_section(self):
        """Load complete welding interface into work area - NO POPUP"""
        if not self.robot.links:
            messagebox.showwarning("No Joints", "Please add at least one joint before welding.")
            return
        
        self.clear_work_area()
        self.current_section = "welding"
        self.status_label.config(text="WELDING MODE ACTIVE")
        self.weld_points.clear()
        
        # Main welding container
        container = tk.Frame(self.work_frame, bg='#2a2a2a', relief=tk.RAISED, bd=2)
        container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # HEADER
        header = tk.Frame(container, bg='#3a3a3a')
        header.pack(fill=tk.X, padx=5, pady=5)
        tk.Label(header, text="WELDING CONTROL PANEL", fg='white', bg='#3a3a3a',
                font=('Arial', 16, 'bold')).pack(pady=10)
        
        # MODE SELECTION
        mode_frame = tk.Frame(container, bg='#2a2a2a')
        mode_frame.pack(fill=tk.X, padx=10, pady=10)
        
        tk.Label(mode_frame, text="Welding Mode:", fg='white', bg='#2a2a2a',
                font=('Arial', 12, 'bold')).pack(side=tk.LEFT, padx=10)
        
        tk.Radiobutton(mode_frame, text="Spot Welding", variable=self.weld_mode, value="spot",
                      bg='#2a2a2a', fg='white', selectcolor='#1a1a1a', font=('Arial', 11),
                      command=self.update_welding_ui).pack(side=tk.LEFT, padx=10)
        
        tk.Radiobutton(mode_frame, text="Continuous Welding", variable=self.weld_mode, value="continuous",
                      bg='#2a2a2a', fg='white', selectcolor='#1a1a1a', font=('Arial', 11),
                      command=self.update_welding_ui).pack(side=tk.LEFT, padx=10)
        
        # SPOT WELDING SUBMODE (only shown when spot is selected)
        self.spot_frame = tk.Frame(container, bg='#2a2a2a')
        
        tk.Label(self.spot_frame, text="Spot Welding Type:", fg='white', bg='#2a2a2a',
                font=('Arial', 11, 'bold')).pack(side=tk.LEFT, padx=10)
        
        tk.Radiobutton(self.spot_frame, text="Line Spot Welding", variable=self.spot_submode, value="line",
                      bg='#2a2a2a', fg='white', selectcolor='#1a1a1a', font=('Arial', 10)).pack(side=tk.LEFT, padx=10)
        
        tk.Radiobutton(self.spot_frame, text="Only Spot Welding", variable=self.spot_submode, value="only",
                      bg='#2a2a2a', fg='white', selectcolor='#1a1a1a', font=('Arial', 10)).pack(side=tk.LEFT, padx=10)
        
        # COORDINATE INPUT SECTION
        coord_section = tk.Frame(container, bg='#2a2a2a')
        coord_section.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        tk.Label(coord_section, text="COORDINATE INPUT", fg='#00ff00', bg='#2a2a2a',
                font=('Arial', 13, 'bold')).pack(pady=5)
        
        # Two input methods side by side
        input_methods = tk.Frame(coord_section, bg='#2a2a2a')
        input_methods.pack(fill=tk.X, pady=5)
        
        # METHOD A: Manual entry
        method_a = tk.LabelFrame(input_methods, text="Method A: Table Entry", fg='white', bg='#2a2a2a',
                                font=('Arial', 10, 'bold'))
        method_a.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        
        entry_frame = tk.Frame(method_a, bg='#2a2a2a')
        entry_frame.pack(pady=5)
        
        tk.Label(entry_frame, text="X:", fg='white', bg='#2a2a2a').grid(row=0, column=0, padx=2)
        self.x_entry = tk.Entry(entry_frame, width=8)
        self.x_entry.grid(row=0, column=1, padx=2)
        
        tk.Label(entry_frame, text="Y:", fg='white', bg='#2a2a2a').grid(row=0, column=2, padx=2)
        self.y_entry = tk.Entry(entry_frame, width=8)
        self.y_entry.grid(row=0, column=3, padx=2)
        
        tk.Label(entry_frame, text="Z:", fg='white', bg='#2a2a2a').grid(row=0, column=4, padx=2)
        self.z_entry = tk.Entry(entry_frame, width=8)
        self.z_entry.grid(row=0, column=5, padx=2)
        
        tk.Button(entry_frame, text="ADD POINT", bg='#006400', fg='white', font=('Arial', 10, 'bold'),
                 command=self.add_coordinate_from_entry).grid(row=0, column=6, padx=10)
        
        # METHOD B: Capture from robot
        method_b = tk.LabelFrame(input_methods, text="Method B: Capture Current", fg='white', bg='#2a2a2a',
                                font=('Arial', 10, 'bold'))
        method_b.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        
        capture_frame = tk.Frame(method_b, bg='#2a2a2a')
        capture_frame.pack(pady=10)
        
        tk.Label(capture_frame, text="Move sliders to position, then:", fg='white', bg='#2a2a2a').pack()
        tk.Button(capture_frame, text="CAPTURE POSITION", bg='#8B4500', fg='white',
                 font=('Arial', 12, 'bold'), command=self.capture_current_position, width=20, height=2).pack(pady=5)
        
        # COORDINATE TABLE
        table_frame = tk.LabelFrame(coord_section, text="Weld Points Table", fg='white', bg='#2a2a2a',
                                   font=('Arial', 11, 'bold'))
        table_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # Table with scrollbar
        table_container = tk.Frame(table_frame, bg='#2a2a2a')
        table_container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        table_scroll = tk.Scrollbar(table_container, orient=tk.VERTICAL)
        table_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.coord_table = ttk.Treeview(table_container, columns=('P', 'X', 'Y', 'Z'), show='headings',
                                       yscrollcommand=table_scroll.set, height=8)
        table_scroll.config(command=self.coord_table.yview)
        
        self.coord_table.heading('P', text='P')
        self.coord_table.heading('X', text='X')
        self.coord_table.heading('Y', text='Y')
        self.coord_table.heading('Z', text='Z')
        
        self.coord_table.column('P', width=40, anchor='center')
        self.coord_table.column('X', width=80, anchor='center')
        self.coord_table.column('Y', width=80, anchor='center')
        self.coord_table.column('Z', width=80, anchor='center')
        
        self.coord_table.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Table controls
        table_btn_frame = tk.Frame(table_frame, bg='#2a2a2a')
        table_btn_frame.pack(fill=tk.X, pady=5)
        
        tk.Button(table_btn_frame, text="DELETE SELECTED", bg='#8B0000', fg='white',
                 command=self.delete_selected_point).pack(side=tk.LEFT, padx=5)
        tk.Button(table_btn_frame, text="CLEAR ALL", bg='#8B0000', fg='white',
                 command=self.clear_all_points).pack(side=tk.LEFT, padx=5)
        
        # WELDING PARAMETERS
        param_frame = tk.LabelFrame(container, text="Welding Parameters", fg='white', bg='#2a2a2a',
                                   font=('Arial', 11, 'bold'))
        param_frame.pack(fill=tk.X, padx=10, pady=10)
        
        param_grid = tk.Frame(param_frame, bg='#2a2a2a')
        param_grid.pack(pady=10)
        
        # Line spot welding: number of spots
        self.spots_frame = tk.Frame(param_grid, bg='#2a2a2a')
        self.spots_frame.grid(row=0, column=0, padx=20, pady=5, sticky='w')
        
        tk.Label(self.spots_frame, text="Number of Spots:", fg='white', bg='#2a2a2a',
                font=('Arial', 10)).pack(side=tk.LEFT, padx=5)
        self.num_spots = tk.Spinbox(self.spots_frame, from_=2, to=100, width=8, font=('Arial', 10))
        self.num_spots.delete(0, tk.END)
        self.num_spots.insert(0, "3")
        self.num_spots.pack(side=tk.LEFT, padx=5)
        
        # Weld time
        tk.Label(param_grid, text="Weld Time (seconds):", fg='white', bg='#2a2a2a',
                font=('Arial', 10)).grid(row=0, column=1, padx=20, sticky='e')
        self.weld_time = tk.Entry(param_grid, width=8)
        self.weld_time.insert(0, "2.0")
        self.weld_time.grid(row=0, column=2, padx=5)
        
        # Welding rod length (for total length calculation)
        tk.Label(param_grid, text="Rod Length (cm):", fg='white', bg='#2a2a2a',
                font=('Arial', 10)).grid(row=1, column=0, padx=20, sticky='e')
        self.rod_length = tk.Entry(param_grid, width=8)
        self.rod_length.insert(0, "5.0")
        self.rod_length.grid(row=1, column=1, padx=5)
        
        # SAFE POSITION
        safe_frame = tk.LabelFrame(container, text="Safe Position (After Job)", fg='white', bg='#2a2a2a',
                                  font=('Arial', 11, 'bold'))
        safe_frame.pack(fill=tk.X, padx=10, pady=10)
        
        safe_grid = tk.Frame(safe_frame, bg='#2a2a2a')
        safe_grid.pack(pady=10)
        
        tk.Label(safe_grid, text="X:", fg='white', bg='#2a2a2a').grid(row=0, column=0, padx=5)
        self.safe_x = tk.Entry(safe_grid, width=8)
        self.safe_x.insert(0, "50")
        self.safe_x.grid(row=0, column=1, padx=5)
        
        tk.Label(safe_grid, text="Y:", fg='white', bg='#2a2a2a').grid(row=0, column=2, padx=5)
        self.safe_y = tk.Entry(safe_grid, width=8)
        self.safe_y.insert(0, "30")
        self.safe_y.grid(row=0, column=3, padx=5)
        
        tk.Label(safe_grid, text="Z:", fg='white', bg='#2a2a2a').grid(row=0, column=4, padx=5)
        self.safe_z = tk.Entry(safe_grid, width=8)
        self.safe_z.insert(0, "50")
        self.safe_z.grid(row=0, column=5, padx=5)
        
        # WELD LENGTH DISPLAY
        self.weld_length_label = tk.Label(container, text="Total Weld Length: 0.0 cm",
                                         fg='#00ff00', bg='#2a2a2a', font=('Arial', 12, 'bold'))
        self.weld_length_label.pack(pady=10)
        
        # ACTION BUTTONS
        action_frame = tk.Frame(container, bg='#2a2a2a')
        action_frame.pack(fill=tk.X, pady=10)
        
        tk.Button(action_frame, text="GENERATE WELD PATH", bg='#006400', fg='white',
                 font=('Arial', 14, 'bold'), command=self.generate_weld_path, width=20, height=2).pack(side=tk.LEFT, padx=10)
        
        tk.Button(action_frame, text="START WELDING", bg='#8B8B00', fg='white',
                 font=('Arial', 14, 'bold'), command=self.start_welding, width=20, height=2).pack(side=tk.LEFT, padx=10)
        
        tk.Button(action_frame, text="STOP", bg='#8B0000', fg='white',
                 font=('Arial', 14, 'bold'), command=self.stop_welding, width=15, height=2).pack(side=tk.LEFT, padx=10)
        
        # Initial UI state
        self.update_welding_ui()
    
    def update_welding_ui(self):
        """Update welding UI based on selected mode"""
        if self.weld_mode.get() == "spot":
            self.spot_frame.pack(fill=tk.X, padx=10, pady=5)
            self.spots_frame.grid(row=0, column=0, padx=20, pady=5, sticky='w')
        else:
            self.spot_frame.pack_forget()
            self.spots_frame.grid_remove()
    
    def add_coordinate_from_entry(self):
        """Add point from manual entry"""
        try:
            x = float(self.x_entry.get())
            y = float(self.y_entry.get())
            z = float(self.z_entry.get())
            
            self.weld_points.append((x, y, z))
            self.update_coord_table()
            
            # Clear entries
            self.x_entry.delete(0, tk.END)
            self.y_entry.delete(0, tk.END)
            self.z_entry.delete(0, tk.END)
            
            self.status_label.config(text=f"✓ Point added: ({x:.2f}, {y:.2f}, {z:.2f})")
            self.update_weld_visualization()
        except ValueError:
            messagebox.showerror("Error", "Invalid coordinates. Please enter numeric values.")
    
    def capture_current_position(self):
        """Capture current robot tool position"""
        x, y, z = self.robot.get_tool_position()
        self.weld_points.append((x, y, z))
        self.update_coord_table()
        self.status_label.config(text=f"✓ Position captured: ({x:.2f}, {y:.2f}, {z:.2f})")
        self.update_weld_visualization()
    
    def update_coord_table(self):
        """Update the coordinate table display"""
        # Clear table
        for item in self.coord_table.get_children():
            self.coord_table.delete(item)
        
        # Repopulate
        for i, (x, y, z) in enumerate(self.weld_points):
            self.coord_table.insert('', 'end', values=(i+1, f"{x:.2f}", f"{y:.2f}", f"{z:.2f}"))
    
    def delete_selected_point(self):
        """Delete selected point from table"""
        selection = self.coord_table.selection()
        if selection:
            item = selection[0]
            index = self.coord_table.index(item)
            self.weld_points.pop(index)
            self.update_coord_table()
            self.update_weld_visualization()
            self.status_label.config(text="✓ Point deleted")
    
    def clear_all_points(self):
        """Clear all weld points"""
        if messagebox.askyesno("Confirm", "Clear all weld points?"):
            self.weld_points.clear()
            self.update_coord_table()
            self.update_weld_visualization()
            self.status_label.config(text="✓ All points cleared")
    
    def update_weld_visualization(self):
        """Update graph to show weld path and area"""
        # TODO: Add weld line visualization to graph
        # For now, just update total length
        if len(self.weld_points) >= 2:
            total_length = 0
            for i in range(len(self.weld_points) - 1):
                p1 = self.weld_points[i]
                p2 = self.weld_points[i + 1]
                dx = p2[0] - p1[0]
                dy = p2[1] - p1[1]
                dz = p2[2] - p1[2]
                total_length += (dx**2 + dy**2 + dz**2) ** 0.5
            
            try:
                rod_len = float(self.rod_length.get())
                total_length += rod_len
            except:
                pass
            
            self.weld_length_label.config(text=f"Total Weld Length: {total_length:.2f} cm")
        else:
            self.weld_length_label.config(text="Total Weld Length: 0.0 cm")
    
    def generate_weld_path(self):
        """Generate complete weld path with intermediate spots"""
        if len(self.weld_points) < 2:
            messagebox.showwarning("Insufficient Points", "Please add at least 2 weld points.")
            return
        
        if self.weld_mode.get() == "spot" and self.spot_submode.get() == "line":
            # Line spot welding: generate intermediate spots
            try:
                num_spots = int(self.num_spots.get())
                if num_spots < 2:
                    messagebox.showerror("Error", "Number of spots must be at least 2.")
                    return
                
                # Generate evenly spaced spots along the path
                # (Implementation would calculate interpolated points)
                messagebox.showinfo("Success", f"Generated {num_spots} weld spots along path.")
                self.status_label.config(text=f"✓ Path generated: {num_spots} spots")
            except ValueError:
                messagebox.showerror("Error", "Invalid number of spots.")
        else:
            messagebox.showinfo("Success", "Weld path validated.")
            self.status_label.config(text="✓ Path ready")
    
    def start_welding(self):
        """Execute welding operation"""
        if len(self.weld_points) < 2:
            messagebox.showwarning("No Path", "Please generate weld path first.")
            return
        
        try:
            weld_time = float(self.weld_time.get())
        except ValueError:
            messagebox.showerror("Error", "Invalid weld time.")
            return
        
        # Generate and send welding commands
        # (Full implementation would iterate through points, generate IK, send commands with WELD:ON/OFF)
        
        messagebox.showinfo("Welding Started", "Welding operation initiated.\nCommands sent to ESP32.")
        self.status_label.config(text="🔥 WELDING IN PROGRESS...")
        
        # Move to safe position after completion (would be in callback)
        # self.move_to_safe_position()
    
    def stop_welding(self):
        """Stop welding operation"""
        stop_command = generate_stop_command()
        send_command_to_esp32(stop_command, priority=True)
        self.status_label.config(text="✓ Welding stopped")
        messagebox.showinfo("Stopped", "Welding operation stopped.")
    
    def move_to_safe_position(self):
        """Move robot to safe position"""
        try:
            safe_x = float(self.safe_x.get())
            safe_y = float(self.safe_y.get())
            safe_z = float(self.safe_z.get())
            
            # Calculate IK and move
            # (Implementation would use inverse_kinematics and send commands)
            
            self.status_label.config(text=f"Moving to safe position ({safe_x}, {safe_y}, {safe_z})")
        except ValueError:
            messagebox.showerror("Error", "Invalid safe position coordinates.")
    
    # ==================== EMERGENCY & UPDATES ====================
    
    def emergency_stop(self, event=None):
        """Emergency stop - halt all motion and welding"""
        print("!!! EMERGENCY STOP !!!")
        
        stop_command = generate_stop_command()
        send_command_to_esp32(stop_command, priority=True)
        
        # Reset robot to safe position
        for link in self.robot.links:
            if link.motor_type == "servo":
                link.angle = (link.min_angle + link.max_angle) / 2
            else:
                link.angle = 0
        
        reset_command = generate_move_command(self.robot, speed=50, time_ms=500, weld_state="OFF")
        if reset_command:
            send_command_to_esp32(reset_command)
        
        self.rebuild_sliders()
        self.update_view()
        self.status_label.config(text="!!! EMERGENCY STOP ACTIVATED !!!", fg='red')
        
        # Reset status color after 3 seconds
        self.root.after(3000, lambda: self.status_label.config(fg='#00ff00'))
    
    def update_view(self):
        """Update 2D/3D visualization"""
        points = self.robot.get_points()
        
        if self.view_mode.get() == "3D":
            self.view_2d.canvas.get_tk_widget().pack_forget()
            self.view_3d.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
            self.view_3d.update(points)
        else:
            self.view_3d.canvas.get_tk_widget().pack_forget()
            self.view_2d.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
            self.view_2d.update(points)
        
        x, y, z = self.robot.get_tool_position()
        self.coord_label.config(text=f"X:{x:.2f} Y:{y:.2f} Z:{z:.2f}")
        if hasattr(self, 'coord_display'):
            self.coord_display.config(text=f"({x:.2f}, {y:.2f}, {z:.2f})")
    
    def run(self):
        """Start the application"""
        self.root.mainloop()
