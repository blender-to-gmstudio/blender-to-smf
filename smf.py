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

# The final list of SMF nodes. Extend this one with others to add
# more transform chains/hierarchies
# All to_node_list functions below add transform hierarchies to this
smf_nodes = [
    root_node,
]

## RIG
def armature_to_node_list(armature_object):
    """Convert an armature's skeleton to a list of SMF nodes"""
    pass

def object_to_node_list(any_object):
    """Convert any scene object to a list of SMF nodes"""
    pass

def hierarchy_to_node_list(root_object):
    """Convert a hierarchy of Blender scene objects to an SMF node hierarchy"""
    pass
