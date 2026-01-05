import math

def inverse_kinematics_xyz(x, y, z, links):
    if len(links) < 2:
        raise ValueError("Need minimum 2 joints")

    l1 = links[0].length
    l2 = links[1].length

    d = math.sqrt(x*x + y*y)
    if d > (l1 + l2):
        raise ValueError("Target unreachable")

    cos2 = (d*d - l1*l1 - l2*l2) / (2*l1*l2)
    a2 = math.acos(cos2)
    a1 = math.atan2(y, x) - math.atan2(l2*math.sin(a2), l1 + l2*math.cos(a2))

    return math.degrees(a1), math.degrees(a2), z
