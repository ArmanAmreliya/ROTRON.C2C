import math
import numpy as np

def forward_kinematics(links):
    """
    Calculate forward kinematics for robot arm.
    All joints start vertically along Z-axis.
    Each joint can rotate around X, Y, or Z axis.
    """
    points = [(0, 0, 0)]
    
    # Current transformation matrix (identity)
    transform = np.eye(4)
    
    for link in links:
        # Rotation angle in radians
        angle_rad = math.radians(link.angle)
        
        # Create rotation matrix based on rotation axis
        if link.rotation_axis == 'X':
            rotation = np.array([
                [1, 0, 0, 0],
                [0, math.cos(angle_rad), -math.sin(angle_rad), 0],
                [0, math.sin(angle_rad), math.cos(angle_rad), 0],
                [0, 0, 0, 1]
            ])
        elif link.rotation_axis == 'Y':
            rotation = np.array([
                [math.cos(angle_rad), 0, math.sin(angle_rad), 0],
                [0, 1, 0, 0],
                [-math.sin(angle_rad), 0, math.cos(angle_rad), 0],
                [0, 0, 0, 1]
            ])
        else:  # Z-axis (default)
            rotation = np.array([
                [math.cos(angle_rad), -math.sin(angle_rad), 0, 0],
                [math.sin(angle_rad), math.cos(angle_rad), 0, 0],
                [0, 0, 1, 0],
                [0, 0, 0, 1]
            ])
        
        # Translation along local Z-axis (joint is vertical)
        translation = np.array([
            [1, 0, 0, 0],
            [0, 1, 0, 0],
            [0, 0, 1, link.length],
            [0, 0, 0, 1]
        ])
        
        # Apply rotation first, then translation
        transform = transform @ rotation @ translation
        
        # Extract position
        x, y, z = transform[0, 3], transform[1, 3], transform[2, 3]
        points.append((x, y, z))
    
    return points
