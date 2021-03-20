# SMF export scripts for Blender
#
#import dq
from .pydq import dq_create_matrix_vector, dq_to_tuple_smf

SMF_version = 7
SMF_format_size = 44
SMF_header_size = 79

SMF_header_string = "SnidrsModelFormat\0"

def export():
    pass

def rig_to_buffer():
    pass

def animation_to_buffer(scene, rig_object, anim):
    animation_bytes = bytearray()
    
    if not anim:
        # No valid animation
        animation_bytes.extend(pack('B', 0))                        # animNum
    else:
        # Single animation in armature object's action
        animation_bytes.extend(pack('B', 1))                        # animNum (one action)
        animation_bytes.extend(bytearray(anim.name + "\0", 'utf-8'))# animName
        
        # Get the times where the animation has keyframes set
        keyframe_times = sorted({p.co[0] for fcurve in rig_object.animation_data.action.fcurves for p in fcurve.keyframe_points})
        keyframe_max = max(keyframe_times)
        
        animation_bytes.extend(pack('B',len(keyframe_times)))       # keyframeNum
        for keyframe in keyframe_times:
            # PRE Armature must be in posed state
            scene.frame_set(keyframe)
            animation_bytes.extend(pack('f', keyframe / keyframe_max))
            for bone in rig_object.pose.bones:
                dq = dq_create_matrix_vector(Matrix(), Vector())
                print(dq)
                animation_bytes.extend(pack('ffffffff',*dq_to_tuple_smf(dq)))
    
    return animation_bytes