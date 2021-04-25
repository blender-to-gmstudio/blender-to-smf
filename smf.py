# SMF export scripts for Blender
#
#from .pydq import dq_create_matrix_vector, dq_to_tuple_smf
import bpy
from struct import Struct

SMF_version = 10
SMF_format_struct = Struct("ffffffffBBBBBBBBBBBB")
SMF_format_size = SMF_format_struct.size            # 44

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

def prep_mesh(obj, obj_rig, mesh):
    pass

def node_list(armature_object):
    """Construct the SMF node list from the given Armature object"""
    pass

def bindmap():
    """"""
    pass

def precalc_weights(armature_object, mesh_objects):
    """Pre-calculate the skinning weights for the given selection of """
    pass

def apply_world_matrix(matrix, matrix_world):
    """Applies the world matrix to the given bone matrix and makes sure scaling effects are ignored."""
    mat_w = matrix_world.copy()
    mat_w @= matrix
    deco = mat_w.decompose()
    t = deco[0]
    mat_w = deco[1].to_matrix().to_4x4()
    mat_w.translation = t[:]
    return mat_w

### IMPORT
from struct import unpack, unpack_from

def unpack_string_from(data, offset=0):
    """Unpacks a zero terminated string from the given offset in the data"""
    result = ""
    while data[offset] != 0:
        result += chr(data[offset])
        offset += 1
    return result

def import_smf(filepath):
    """Main entry point for SMF import"""
    import bmesh
    
    data = bytearray()
    with open(filepath, 'rb') as file:
        data = file.read()
    
    header_bytes = unpack_from("17s", data)[0]
    header_text = "".join([chr(b) for b in header_bytes])
    #print(header_text)
    
    if header_text == "SnidrsModelFormat":
        # Valid SMF v7 file
        versionNum = unpack_from("f", data, offset=18)[0]
        print(versionNum)
        
        if int(versionNum) == 7:
            texPos = unpack_from("I", data, offset=18+4)[0]
            matPos = unpack_from("I", data, offset=18+4+4)[0]
            modPos = unpack_from("I", data, offset=18+4+4+4)[0]
            nodPos = unpack_from("I", data, offset=18+4+4+4+4)[0]
            colPos = unpack_from("I", data, offset=18+4+4+4+4+4)[0]
            rigPos = unpack_from("I", data, offset=18+4+4+4+4+4+4)[0]
            aniPos = unpack_from("I", data, offset=18+4+4+4+4+4+4+4)[0]
            selPos = unpack_from("I", data, offset=18+4+4+4+4+4+4+4+4)[0]
            subPos = unpack_from("I", data, offset=18+4+4+4+4+4+4+4+4+4)[0]
            placeholder = unpack_from("I", data, offset = 18+4+4+4+4+4+4+4+4+4+4)[0]
            modelNum = unpack_from("B", data, offset = 18+4+4+4+4+4+4+4+4+4+4+4)[0]
            print(texPos, matPos, modPos, nodPos, colPos, rigPos, aniPos, selPos, subPos)
            print(placeholder)
            print(modelNum)
            
            img = None
            
            n = unpack_from("B", data, offset=texPos)[0]
            print("Textures: ", n)
            
            # Read texture images
            offset = texPos+1
            for i in range(0, n):
                name = unpack_string_from(data, offset)
                print(name)
                offset = offset + len(name) + 1
                dimensions = (
                    unpack_from("H", data, offset=offset)[0],
                    unpack_from("H", data, offset=offset+2)[0],
                )
                offset = offset+4
                print(name)
                print(dimensions)
                if name in bpy.data.images:
                    # Already an image with the given name
                    img = bpy.data.images[name]
                else:
                    # No image with this name exists, add a new one
                    img = bpy.data.images.new(name=name, width=dimensions[0], height=dimensions[1])
                    for i in range(0, dimensions[0]*dimensions[1]):
                         rgba = data[offset+i*4:offset+i*4+4]
                         rgba = [co/255 for co in rgba]
                         img.pixels[i*4:i*4+4] = rgba[:]
            
            # Read model data
            size = unpack_from("I", data, offset=modPos)[0]
            pos = modPos + 4
            print(size)
            no_faces = int(size/3 / SMF_format_size)
            print(no_faces)
            
            bm = bmesh.new()
            uv_layer = bm.loops.layers.uv.verify()
            for i in range(no_faces):
                v = []
                uvs = []
                for j in range(3):
                    v_data = SMF_format_struct.unpack_from(data, pos)
                    pos = pos + SMF_format_struct.size
                    co = v_data[0:3]
                    nml = v_data[3:6]
                    uv = v_data[6:8]
                    tan = v_data[8:11]
                    indices = v_data[11:15]
                    weights = v_data[15:19]
                    #print(pos, co, nml, uv, tan, indices, weights)
                    v.append(bm.verts.new(co))
                    uvs.append(uv)
                face = bm.faces.new(v)
                
                for i in range(len(face.loops)):
                    face.loops[i][uv_layer].uv = uvs[i]
            
            mesh = bpy.data.meshes.new("ImportedFromSMF")
            bm.to_mesh(mesh)
            
            matName = unpack_string_from(data, offset=pos)
            pos = pos + len(matName) + 1
            texName = unpack_string_from(data, offset=pos)
            pos = pos + len(texName) + 1
            print(matName, texName)
            
            bpy.ops.object.add(type="MESH")
            new_obj = bpy.context.active_object
            new_obj.data = mesh
            
            bpy.ops.object.material_slot_add()
            bpy.ops.material.new()
            mat = bpy.data.materials[len(bpy.data.materials)-1]
            mat.name = matName
            new_obj.material_slots[0].material = mat
            mat.node_tree.nodes.new(type="ShaderNodeTexImage") # This is the bl_rna identifier, NOT the type!
            image_node = mat.node_tree.nodes['Image Texture']
            image_node.image = img
            shader_node = mat.node_tree.nodes["Principled BSDF"]
            mat.node_tree.links.new(image_node.outputs['Color'], shader_node.inputs['Base Color'])
    
    return {'FINISHED'}