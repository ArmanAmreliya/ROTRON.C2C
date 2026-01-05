"""Add Joint Dialog - Modal popup for adding new joints"""

import tkinter as tk
from tkinter import ttk, messagebox


class AddJointDialog:
    def __init__(self, parent):
        self.result = None
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Add Joint")
        self.dialog.geometry("400x600")
        self.dialog.configure(bg='#2a2a2a')
        self.dialog.resizable(False, False)
        
        # Make it modal
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        # Center on parent
        self.dialog.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - self.dialog.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.dialog.winfo_height()) // 2
        self.dialog.geometry(f"+{x}+{y}")
        
        self._create_widgets()
        
    def _create_widgets(self):
        """Create all dialog widgets"""
        main_frame = tk.Frame(self.dialog, bg='#2a2a2a', padx=20, pady=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # ===== SECTION 1: Joint Length =====
        length_frame = tk.LabelFrame(main_frame, text="Joint Length", 
                                     bg='#2a2a2a', fg='white',
                                     font=('Arial', 11, 'bold'), padx=10, pady=10)
        length_frame.pack(fill=tk.X, pady=(0, 15))
        
        length_label = tk.Label(length_frame, text="Joint Length (cm):", 
                               bg='#2a2a2a', fg='white', font=('Arial', 10))
        length_label.pack(anchor=tk.W, pady=(0, 5))
        
        self.length_entry = tk.Entry(length_frame, font=('Arial', 12), 
                                     bg='#3a3a3a', fg='white', 
                                     insertbackground='white', width=15)
        self.length_entry.insert(0, "10.0")
        self.length_entry.pack(fill=tk.X)
        
        # ===== SECTION 2: Motor Type =====
        motor_frame = tk.LabelFrame(main_frame, text="Motor Type", 
                                   bg='#2a2a2a', fg='white',
                                   font=('Arial', 11, 'bold'), padx=10, pady=10)
        motor_frame.pack(fill=tk.X, pady=(0, 15))
        
        self.motor_type = tk.StringVar(value="servo")
        
        servo_radio = tk.Radiobutton(motor_frame, text="Servo Motor", 
                                    variable=self.motor_type, value="servo",
                                    bg='#2a2a2a', fg='white', 
                                    selectcolor='#3a3a3a',
                                    font=('Arial', 10),
                                    command=self._on_motor_type_change)
        servo_radio.pack(anchor=tk.W, pady=2)
        
        stepper_radio = tk.Radiobutton(motor_frame, text="Stepper Motor", 
                                      variable=self.motor_type, value="stepper",
                                      bg='#2a2a2a', fg='white', 
                                      selectcolor='#3a3a3a',
                                      font=('Arial', 10),
                                      command=self._on_motor_type_change)
        stepper_radio.pack(anchor=tk.W, pady=2)
        
        # ===== SECTION 3: Motor Parameters =====
        params_frame = tk.LabelFrame(main_frame, text="Motor Parameters", 
                                    bg='#2a2a2a', fg='white',
                                    font=('Arial', 11, 'bold'), padx=10, pady=10)
        params_frame.pack(fill=tk.X, pady=(0, 15))
        
        # Servo parameters
        self.servo_params_frame = tk.Frame(params_frame, bg='#2a2a2a')
        self.servo_params_frame.pack(fill=tk.X)
        
        max_angle_label = tk.Label(self.servo_params_frame, 
                                  text="Max Rotation Angle (°):", 
                                  bg='#2a2a2a', fg='white', font=('Arial', 10))
        max_angle_label.pack(anchor=tk.W, pady=(0, 5))
        
        self.max_angle_entry = tk.Entry(self.servo_params_frame, font=('Arial', 12), 
                                       bg='#3a3a3a', fg='white', 
                                       insertbackground='white', width=15)
        self.max_angle_entry.insert(0, "180")
        self.max_angle_entry.pack(fill=tk.X)
        
        servo_info = tk.Label(self.servo_params_frame, 
                            text="(Slider range: 0 to max angle\nCenter = max/2, vertical position at center)", 
                            bg='#2a2a2a', fg='#888888', font=('Arial', 8), 
                            justify=tk.LEFT)
        servo_info.pack(anchor=tk.W, pady=(5, 0))
        
        # Stepper parameters (info only)
        self.stepper_params_frame = tk.Frame(params_frame, bg='#2a2a2a')
        
        stepper_info = tk.Label(self.stepper_params_frame, 
                               text="Rotation Range: 0° to 360°\nNo center offset - starts at 0°", 
                               bg='#2a2a2a', fg='#888888', font=('Arial', 9), 
                               justify=tk.LEFT)
        stepper_info.pack(anchor=tk.W, pady=5)
        
        # ===== SECTION 4: Rotation Axis =====
        axis_frame = tk.LabelFrame(main_frame, text="Rotation Axis", 
                                  bg='#2a2a2a', fg='white',
                                  font=('Arial', 11, 'bold'), padx=10, pady=10)
        axis_frame.pack(fill=tk.X, pady=(0, 15))
        
        axis_label = tk.Label(axis_frame, text="Rotate in:", 
                             bg='#2a2a2a', fg='white', font=('Arial', 10))
        axis_label.pack(anchor=tk.W, pady=(0, 5))
        
        self.rotation_axis = tk.StringVar(value="Z")
        
        axis_buttons_frame = tk.Frame(axis_frame, bg='#2a2a2a')
        axis_buttons_frame.pack(fill=tk.X)
        
        x_radio = tk.Radiobutton(axis_buttons_frame, text="X-axis", 
                                variable=self.rotation_axis, value="X",
                                bg='#2a2a2a', fg='white', 
                                selectcolor='#3a3a3a',
                                font=('Arial', 10))
        x_radio.pack(side=tk.LEFT, padx=5)
        
        y_radio = tk.Radiobutton(axis_buttons_frame, text="Y-axis", 
                                variable=self.rotation_axis, value="Y",
                                bg='#2a2a2a', fg='white', 
                                selectcolor='#3a3a3a',
                                font=('Arial', 10))
        y_radio.pack(side=tk.LEFT, padx=5)
        
        z_radio = tk.Radiobutton(axis_buttons_frame, text="Z-axis", 
                                variable=self.rotation_axis, value="Z",
                                bg='#2a2a2a', fg='white', 
                                selectcolor='#3a3a3a',
                                font=('Arial', 10))
        z_radio.pack(side=tk.LEFT, padx=5)
        
        # ===== SECTION 5: Buttons =====
        button_frame = tk.Frame(main_frame, bg='#2a2a2a')
        button_frame.pack(fill=tk.X, pady=(15, 0))
        
        add_btn = tk.Button(button_frame, text="Add Joint", 
                           bg='#006400', fg='white',
                           font=('Arial', 12, 'bold'), 
                           width=12, height=2,
                           command=self._on_add)
        add_btn.pack(side=tk.LEFT, padx=5, expand=True)
        
        cancel_btn = tk.Button(button_frame, text="Cancel", 
                              bg='#8B0000', fg='white',
                              font=('Arial', 12, 'bold'), 
                              width=12, height=2,
                              command=self._on_cancel)
        cancel_btn.pack(side=tk.LEFT, padx=5, expand=True)
        
        # Initialize motor type display
        self._on_motor_type_change()
        
    def _on_motor_type_change(self):
        """Show/hide parameters based on motor type"""
        if self.motor_type.get() == "servo":
            self.stepper_params_frame.pack_forget()
            self.servo_params_frame.pack(fill=tk.X)
        else:
            self.servo_params_frame.pack_forget()
            self.stepper_params_frame.pack(fill=tk.X)
    
    def _on_add(self):
        """Validate and return joint parameters"""
        try:
            # Validate length
            length = float(self.length_entry.get())
            if length <= 0:
                messagebox.showerror("Invalid Input", 
                                   "Joint length must be greater than 0 cm",
                                   parent=self.dialog)
                return
            
            motor_type = self.motor_type.get()
            
            # Set angle parameters based on motor type
            if motor_type == "servo":
                max_angle = float(self.max_angle_entry.get())
                if max_angle <= 0:
                    messagebox.showerror("Invalid Input", 
                                       "Max angle must be greater than 0°",
                                       parent=self.dialog)
                    return
                min_angle = 0
            else:  # stepper
                min_angle = 0
                max_angle = 360
            
            rotation_axis = self.rotation_axis.get()
            
            # Store result
            self.result = {
                'length': length,
                'motor_type': motor_type,
                'min_angle': min_angle,
                'max_angle': max_angle,
                'rotation_axis': rotation_axis
            }
            
            self.dialog.destroy()
            
        except ValueError:
            messagebox.showerror("Invalid Input", 
                               "Please enter valid numeric values",
                               parent=self.dialog)
    
    def _on_cancel(self):
        """Cancel and close dialog"""
        self.result = None
        self.dialog.destroy()
    
    def show(self):
        """Show dialog and wait for result"""
        self.dialog.wait_window()
        return self.result
