# SMF script equivalents for Blender
#
# DQs are stored as a named tuple of 2 Quaternions
# and can be converted to a tuple for export to SMF using dq_to_tuple_xyzw
#
from collections import namedtuple
from mathutils import Quaternion

# TODO Derive from typing.NamedTuple? Use dataclasses.dataclass?
DQ = namedtuple(
    'DQ',
    "real dual",
    defaults=[Quaternion(), Quaternion((0, 0, 0, 0))]
)

def dq_create_identity():
    """Return a new identity DQ"""
    return DQ(Quaternion(), Quaternion([0, 0, 0, 0]))

def dq_create_rotation_axis_angle(axis, angle):
    """Return a new pure rotation DQ i.e. with no translation"""
    return DQ(Quaternion(axis, angle), Quaternion([0, 0, 0, 0]))

def dq_create_rotation_quat(quat):
    """Return a new pure rotation DQ i.e. with no translation"""
    return DQ(quat.copy(), Quaternion([0, 0, 0, 0]))

def dq_create_translation(tx, ty, tz):
    """Return a new pure translation DQ i.e. with no rotation"""
    return DQ(Quaternion(), Quaternion([0, tx / 2, ty / 2, tz /2]))

def dq_create_matrix_vector(matrix, vector):
    """Return a new DQ from the given rotation matrix and translation vector"""
    real = matrix.to_quaternion()
    return DQ(real, .5 * Quaternion([0, *vector]) @ real)

def dq_create_matrix(matrix):
    """Return a new DQ from the given 4x4 matrix, which includes a translation vector"""
    translation = matrix.col[3][0:3]
    real = matrix.to_quaternion()
    return DQ(real, .5 * Quaternion([0, *translation]) @ real)

def dq_create_axis_angle_vector(axis, angle, vector):
    """Return a new DQ from the given axis/angle and translation vector"""
    real = Quaternion(axis, angle)
    return DQ(real, .5 * Quaternion([0, *vector]) @ real)

def dq_get_sum(dq1, dq2):
    """Return the sum of dq1 and dq2 as a new DQ"""
    return DQ(dq1.real + dq2.real, dq1.dual + dq2.dual)

def dq_get_product(dq1, dq2):
    """Return the product of dq1 and dq2 as a new DQ"""
    return DQ(dq1.real @ dq2.real,
              dq1.real @ dq2.dual + dq1.dual @ dq2.real)

def dq_get_conjugate(dq):
    """Return a new DQ that is the conjugate of dq"""
    return DQ(dq.real.conjugated(), dq.dual.conjugated())

def dq_rotate(dq, quat):
    """Rotate the DQ dq around quaternion quat"""
    pass

def dq_transform_point(dq, point):
    """Rotate the given point by the DQ"""
    # q' = q * p * q*
    # TODO
    #return DQ()

def dq_normalize(dq):
    """Normalize a dual quaternion"""
    l = 1 / dq.real.magnitude
    dq.real.normalize()

    d = dq.real.dot(dq.dual)
    # d = dq.real[0] * dq.dual[0] + dq.real[1] * dq.dual[1] + dq.real[2] * dq.dual[2] + dq.real[3] * dq.dual[3]
    dq.dual[0] = (dq.dual[0] - dq.real[0] * d) * l
    dq.dual[1] = (dq.dual[1] - dq.real[1] * d) * l
    dq.dual[2] = (dq.dual[2] - dq.real[2] * d) * l
    dq.dual[3] = (dq.dual[3] - dq.real[3] * d) * l
    return dq

def dq_negate(dq):
    """Negate a dual quaternion, i.e. negate both real and dual components"""
    dq.real.negate()
    dq.dual.negate()
    return dq

def dq_negated(dq):
    """Return a new dual quaternion that is the negated dual quaternion"""
    return DQ(-dq.real, -dq.dual)

def dq_invert(dq):
    """Invert a dual quaternion"""
    pass

def dq_to_tuple_xyzw(dq):
    """Return the tuple representation of the given DQ with w last (e.g. for use with SMF)"""
    return (dq.real.x, dq.real.y, dq.real.z, dq.real.w,
            dq.dual.x, dq.dual.y, dq.dual.z, dq.dual.w,)

def dq_to_tuple_wxyz(dq):
    """Return the tuple representation of the given DQ with w first"""
    return (dq.real.w, dq.real.x, dq.real.y, dq.real.z,
            dq.dual.w, dq.dual.x, dq.dual.y, dq.dual.z,)

def dq_get_translation(dq):
    pass

def dq_set_translation(dq, x, y, z):
    pass

def dq_add_translation(dq, x, y, z):
    pass

def dq_get_quotient(dq1, dq2):
    """Return the quotient of dq1 and dq2 as a new DQ"""
    pass
