## All kinds of functions to convert Blender data to SMF data
##
##

from . import pydq

from .pydq import (
    dq_create_identity,
    dq_to_tuple_xyzw,
)

dq_identity = dq_to_tuple_xyzw(dq_create_identity())

# An ordered piece of data for default virtual "root" node for all SMF nodes
root_node = [
    dq_identity,
    0,
    False,
    False,
    (0, 0, 0),
]

class SMF_rig:

    pass

# TODO
class SMF_node:
    """Potential idea for an SMF 'node' class"""
    pass

# The final list of SMF nodes. Extend this one with others to add
# more transform chains/hierarchies
# All to_node_list functions below add transform hierarchies to this
smf_nodes = [
    root_node,
]

def add_node(transform_matrix, parent, is_bone):
    """Add a new node to the SMF rig"""
    global smf_nodes



    smf_nodes.append([
        dq_to_tuple_xyzw(dq_create_matrix(transform_matrix)),

    ])



## RIG
def armature_to_node_list(armature_object):
    """Convert an armature's skeleton to a list of SMF nodes"""
    global smf_nodes

    armature = armature_object.data
    bones = [bone for bone in armature.bones]
    bones_orig = bones.copy()
    for bone in bones_orig:
        # Add a node for each bone (representing the tail)

        if bone.parent and not bone.use_connect:
            # Add an additional node for disconnected bones
            pos = bones.index(bone)
            bones.insert(pos, None)

    for n, bone in enumerate(bones):
        b = bone if bone else bones[n+1]

        parent_bone_index = 0 if not b.parent else bones.index(b.parent)
        connected = b.use_connect

        if bone and b.parent and not b.use_connect:
            # This is a node for which an added node has been written
            parent_bone_index = n-1
            connected = True
            bones[parent_bone_index] = False            # This makes sure the "if bone" check keeps returning False!

        # Construct node matrix
        position_attr = 'tail_local' if bone else 'head_local'
        matrix = b.matrix_local.copy()
        matrix.translation = getattr(b, position_attr)[:]

    # Add node next (TODO!)


    pass

def object_to_node_list(any_object):
    """Convert any scene object to a list of SMF nodes"""
    pass

def hierarchy_to_node_list(root_object):
    """Convert a hierarchy of Blender scene objects to an SMF node hierarchy"""
    pass
