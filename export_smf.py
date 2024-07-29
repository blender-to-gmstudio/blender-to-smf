# SMF export scripts for Blender
#

from struct import Struct, pack, calcsize
from mathutils import *
from math import *

import numpy as np

# Make sure to reload changes to code that we maintain ourselves
# when reloading scripts in Blender
if "bpy" in locals():
    import importlib
    if "pydq" in locals():
        importlib.reload(pydq)

import bpy


# from .debug import format_iterable, print_dq_list

from . import pydq

from .pydq import (
    dq_create_matrix,
    dq_get_product,
    dq_get_conjugate,
    dq_negate,
    dq_to_tuple_xyzw,
)

SMF_version = 11    # SMF 'export' version
SMF_format_struct = Struct("ffffffffBBBBBBBBBBBB")  # 44 bytes
SMF_format_size = SMF_format_struct.size

# Check Blender version
version = bpy.app.version
b41_up = version[0] == 4 and version[1] >= 1  # Blender 4.1 and up

### EXPORT ###

# Mesh-like objects (the ones that can be converted to mesh)
meshlike_types = {'MESH', 'CURVE', 'SURFACE', 'FONT', 'META'}

def prep_mesh(obj, mesh):
    """Prepare the given mesh for export to SMF"""

    # Transform to world coordinates
    mat = Matrix.Scale(-1, 4, Vector([0, 1, 0]))
    mesh.transform(obj.matrix_world)

    # Invert Y
    mesh.transform(mat)
    mesh.flip_normals()

    # Calculate all needed data
    mesh.calc_loop_triangles()
    mesh.calc_tangents()
    if not b41_up:
        mesh.calc_normals_split()

def smf_node_list(armature_object):
    """Construct the SMF node list from the given Armature object"""
    # TODO Insert root node (optional?)
    armature = armature_object.data
    bones = [bone for bone in armature.bones]
    bones_orig = bones.copy()
    for bone in bones_orig:
        if bone.parent and not bone.use_connect:
            pos = bones.index(bone)
            bones.insert(pos, None)
    return bones

def smf_bindmap(bones):
    """Construct the SMF bindmap from the given list of Blender bones"""
    # Create the bindmap (i.e. which bones get sent to the shader in SMF)
    # See smf_rig.update_bindmap (we only need the bindmap part here!)
    # Only consider Blender bones that map to SMF bones
    # Every SMF node that has a parent and is attached to it, represents a bone
    # (the detached nodes represent the heads of bones)
    smf_bones = [b for b in bones if b and b.parent]
    bindmap = {}
    sample_bone_ind = 0
    for node in smf_bones:
        bindmap[node.name] = sample_bone_ind
        sample_bone_ind = sample_bone_ind + 1
    return bindmap

def smf_skin_indices_weights(vertices, index_map, num_influences=4):
    """Get skinning info from all vertices"""
    # This requires the list of vertices and the direct mapping
    # of Blender vertex group index to SMF bone index
    iter = range(len(vertices))
    indices = [[0, 0, 0, 0] for i in iter]          # Use list comprehension
    weights = [[1, 0, 0, 0] for i in iter]          # for fast initialization
    for v in vertices:
        # Only keep the vertex groups used for skinning
        mod_groups = [group for group in v.groups
                      if group.group in index_map.keys()]
        # Filter all vertex group assignments with a weight of 0
        # See bpy.ops.object.vertex_group_clean
        groups = filter(lambda group: (group.weight > 0.0), mod_groups)
        # Keep the highest "num_influences" weights (SMF supports a maximum of 4)
        # See bpy.ops.object.vertex_group_limit_total
        groups = sorted(groups, key=lambda group: group.weight)[-num_influences:]
        s = sum([g.weight for g in groups])
        # Write the highest weights (the others remain at 0, so don't contribute)
        for index, group in enumerate(groups):
            w = group.weight/s*255
            indices[v.index][index] = index_map[group.group]
            weights[v.index][index] = int(w if w <= 255 else 255) # ubyte range!

    return (indices, weights)

def export_smf_file(operator, context,
               filepath,
               export_textures,
               export_type,
               anim_export_mode,
               anim_length_mode,
               multiplier,
               subdivisions,
               interpolation,
               invert_uv_v,
               bone_influences,
               **kwargs,
               ):
    """
    Main entry point for SMF export
    """

    # Figure out what we're going to export
    object_list = context.selected_objects
    #model_list = [o for o in object_list if o.type=='MESH']
    model_list = [o for o in object_list if o.type in meshlike_types]
    armature_list = [o for o in object_list if o.type=='ARMATURE']

    rig_object = None
    rig = None
    anim = None
    animations = dict()     # Use a dictionary to preserve order of insertion!
    if armature_list:
        rig_object = armature_list[0]
        rig = rig_object.data
        anim_data = rig_object.animation_data
        if anim_data:
            if anim_export_mode == 'LNK':
                # Unique actions linked to NLA tracks
                tracks = anim_data.nla_tracks
                if tracks:
                    for track in tracks:
                        for strip in track.strips:
                            animations[strip.action] = strip.action
            elif anim_export_mode == 'CUR':
                # Currently assigned action
                if anim_data.action:
                    animations[anim_data.action] = anim_data.action
            elif anim_export_mode == 'TRA':
                # Every track separately
                pass
            elif anim_export_mode == 'SCN':
                # Final result of NLA tracks on scene
                pass
            else:
                pass

    # Make sure we don't try to export actions that look like they're linked
    # but don't exist anymore
    if None in animations:
        del animations[None]

    # Initalize variables that we need across chunks
    bindmap = {}
    bone_names = []

    # Write rig
    rig_bytes = bytearray()

    if not rig:
        # No (valid) armature for export
        rig_bytes.extend(pack('I', 0))                              # nodeNum
    else:
        # Construct node list for SMF
        # (heads of disconnected bones need to become nodes, too)
        bones = smf_node_list(rig_object)

        # Get the bindmap and relevant bone names
        bindmap = smf_bindmap(bones)
        bone_names = bindmap.keys()

        rig_bytes.extend(pack('I', len(bones)))                     # nodeNum

        if not rig.bones:
            #self.report({'WARNING'},"Armature has no bones. Exporting empty rig.")
            pass

        print("RIG")
        print("---")
        debug_rig = []
        debug_vals = []
        # Make sure to have a root bone!
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

            # Add the world transform to the nodes, ignore scale
            mat_w = apply_world_matrix(matrix, rig_object.matrix_world)
            
            dq = dq_negate(dq_create_matrix(mat_w)) # negate != invert (!!)
            vals = dq_to_tuple_xyzw(dq)

            rig_bytes.extend(pack('f'*len(vals), *vals))
            rig_bytes.extend(pack('I',parent_bone_index))       # node[@ eAnimNode.Parent]
            rig_bytes.extend(pack('B',connected))               # node[@ eAnimNode.IsBone]
            rig_bytes.extend(pack('B',False))                   # node[@ eAnimNode.Locked]
            rig_bytes.extend(pack('fff',*(0, 0, 0)))            # Primary IK axis (default all zeroes)

            t = mat_w.translation
            name = b.name if position_attr == 'tail_local' else "Inserted for " + b.name
            debug_rig.append((n, name, t[0], t[1], t[2], parent_bone_index, connected))
            debug_vals.append(str(["{0:.3f}".format(elem) for elem in vals]))

        # Print some extended, readable debug info
        print("SMF Node List")
        print("-------------")
        for i, d in enumerate(debug_rig):
            s = "{0:>4d} ({5:<3d}, {6:d}) - {1:<40} {2:<.3f} {3:<.3f} {4:<.3f}".format(*d)
            print(s)
            print(debug_vals[i])

    # Write models, list the unique Blender materials in use while we're at it
    dg = bpy.context.evaluated_depsgraph_get()      # We'll need this thing soon
    unique_materials = set()
    unique_images = set()
    model_bytes = bytearray()
    model_number = 0
    model_bytes.extend(pack('B', model_number))     # Reserve a byte for model count
    for obj in model_list:
        # Create a triangulated copy of the mesh
        # that has everything applied (modifiers, transforms, etc.)

        # First, see if this mesh object has an Armature modifier set
        # Set to rest pose if that's the case
        # TODO What else needs to be done here for this to work flawlessly?
        mods = [mod for mod in obj.modifiers if mod.type == "ARMATURE"]
        arma = None
        if mods and mods[0].object:
                arma = mods[0].object.data
                arma_prev_position = arma.pose_position
                arma.pose_position = 'REST'

        # Update the depsgraph!
        # This is important since it actually applies
        # the change to 'REST' position to the data
        dg.update()

        # The new way of doing things using the context depsgraph
        # Get an evaluated version of the current object
        # This includes modifiers, etc.
        # The world transform is not applied to the mesh
        obj_eval = obj.evaluated_get(dg)
        mesh = bpy.data.meshes.new_from_object(obj_eval, preserve_all_data_layers=True, depsgraph=dg)
        prep_mesh(obj, mesh)

        # Reset pose_position setting
        if arma:
            arma.pose_position = arma_prev_position

        # Get a direct mapping between vertex group index and SMF index
        valid_indices = [i for (i, vg) in enumerate(obj.vertex_groups)
                         if vg.name in bone_names]
        vgid_to_smf_map = {i: bindmap[obj.vertex_groups[i].name]
                           for i in valid_indices}

        # Precalculate skinning info for this mesh's vertices
        skin_indices, skin_weights = smf_skin_indices_weights(
            mesh.vertices,
            vgid_to_smf_map,
            bone_influences
        )

        # Write vertex buffer contents
        # First create bytearrays for every material slot
        # (Some may stay empty in case not a single face uses the slot!)
        ba_count = len(obj.material_slots) if obj.material_slots else 1
        data = [bytearray() for i in range(ba_count)]

        uv_data = mesh.uv_layers.active.data if mesh.uv_layers else None

        # Loop through all polygons and write data to appropriate bytearray

        # This way we only need to loop through the data once and don't
        # have to do any grouping of the data by material.
        # This happens implicitly through the indexing by face.material_index
        # In the end we are left with a bytearray per material slot.
        # A bytearray that's empty at the end indicates no faces use the slot
        # and thus can be skipped.
        for face in mesh.loop_triangles:
            for loop in [mesh.loops[i] for i in face.loops]:
                vertex_data = []

                vert = mesh.vertices[loop.vertex_index]

                uv = uv_data[loop.index].uv if uv_data else [0, 0]
                if invert_uv_v:
                    uv[1] = 1 - uv[1]
                tan_int = [*(int((c+1)*127) for c in loop.tangent), 0]

                vertex_data.extend(vert.co)
                vertex_data.extend(loop.normal)
                vertex_data.extend(uv)
                vertex_data.extend(tan_int)
                vertex_data.extend(skin_indices[vert.index])
                vertex_data.extend(skin_weights[vert.index])

                vertex_bytedata = SMF_format_struct.pack(*vertex_data)
                data[face.material_index].extend(vertex_bytedata)

        # Now write an SMF model per bytearray that isn't empty ("if ba")
        # Retrieve unique materials and textures/images too!
        for index, ba in [(index, ba) for (index, ba) in enumerate(data) if ba]:
            model_number += 1
            model_bytes.extend(pack('I', len(ba)))
            model_bytes.extend(ba)
            mat = None
            if obj.material_slots:
                mat = obj.material_slots[index].material
            img = None
            if mat:
                unique_materials.add(mat)
                img = texture_image_from_node_tree(mat)
                if img:
                    unique_images.add(img)
            mat_name = mat.name if mat else ""
            img_name = img.name if img else ""
            model_bytes.extend(bytearray(mat_name + '\0', 'utf-8'))
            model_bytes.extend(bytearray(img_name + '\0', 'utf-8'))
            model_bytes.extend(pack('B',int(not obj.hide_viewport)))

        # Delete triangulated copy of the mesh
        bpy.data.meshes.remove(mesh)

    # Now write the correct model count
    model_bytes[0] =  model_number

    # Write textures and their image data (same thing as seen from SMF)

    texture_bytes = bytearray()
    if export_textures:
        texture_bytes.extend(pack('B', len(unique_images)))             # Number of unique images
        for img in unique_images:
            texture_bytes.extend(bytearray(img.name + "\0",'utf-8'))    # Texture name
            texture_bytes.extend(pack('HH', *img.size))                 # Texture size (w,h)

            # TODO Proper solution to this, ideally extend texture dimensions
            for cpo in img.size:
                if floor(log2(cpo)) != log2(cpo):
                    operator.report({'WARNING'}, img.name + " - dimension is not a power of two: " + str(cpo))

            # Faster way using NumPy and Image.pixels.foreach_set (fast!)
            image_data = np.empty(len(img.pixels), dtype = np.single)
            img.pixels.foreach_get(image_data)
            image_data = (np.multiply(image_data, 255, out=image_data)).round(out=image_data).astype(np.ubyte)
            bytedata = image_data.tobytes()

            texture_bytes.extend(pack('B' * len(img.pixels), *bytedata))
    else:
        texture_bytes.extend(pack('B', 0))

    # Write animations
    animation_bytes = bytearray()

    def write_animation_data(name, scene, byte_data, rig_object, keyframe_times, frame_max, fps, interpolation):
        """Writes all animation data to bytearray byte_data. Used to keep the code a bit tidy."""
        frame_number = len(keyframe_times)
        animation_bytes.extend(bytearray(name + "\0", 'utf-8'))     # animName
        animation_bytes.extend(pack('B', True))                     # loop
        animation_bytes.extend(pack('f', frame_max/fps*1000))       # playTime (ms)
        animation_bytes.extend(pack('B', interpolation))            # interpolation (0, 1, 2)
        animation_bytes.extend(pack('B', multiplier))               # sampleFrameMultiplier
        animation_bytes.extend(pack('I', frame_number))             # animFrameNumber

        # PRE Skeleton must be in Pose Position (see Armature.pose_position)
        frame_prev = scene.frame_current
        for kf_time in keyframe_times:
            subframe, frame = modf(kf_time)
            scene.frame_set(int(frame), subframe=subframe)

            smf_kf_time = kf_time/frame_max

            byte_data.extend(pack('f', smf_kf_time))

            print("Blender frame ", kf_time, " at SMF time ", smf_kf_time)

            # Loop through the armature's PoseBones using the bone/node order we got earlier
            # This guarantees a correct mapping of PoseBones to Bones
            #for rbone in rig_object.data.bones:
            # for i, rbone in enumerate(bones):
            for rbone in bones:
                if rbone:
                    # Get the bone (The name is identical (!))
                    bone = rig_object.pose.bones[rbone.name]

                    # Use bone matrix
                    mat = bone.matrix.copy()
                else:
                    # Use an identity matrix (i.e. no change)
                    mat = Matrix()

                mat.translation = bone.tail[:]
                mat_final = apply_world_matrix(mat, rig_object.matrix_world)
                mat_final.normalize()
                dq = dq_negate(dq_create_matrix(mat_final)) # negate != invert (!!)
                # print(format_iterable(dq_to_tuple_xyzw(dq)))

                # TODO fix_keyframe_dq should go here...

                # m = mat_final.to_3x3()  # Verify orthogonality of upper 3x3
                # print(m)
                # print(m.is_orthogonal)
                # print(m.is_orthogonal_axis_vectors)
                # vals = [j for i in mat_final.col for j in i]
                vals = dq_to_tuple_xyzw(dq)
                byte_data.extend(pack('f'*len(vals), *vals))

        # Restore frame position
        scene.frame_set(int(frame_prev))

    # Export each NLA track linked to the armature object as an animation
    # (use the first action's name as the animation name for now)
    print("ANIMATION")
    print("---------")

    # Common variables
    render = context.scene.render
    fps = render.fps/render.fps_base

    # Write all animations (i.e. actions)
    # TODO
    if anim_export_mode == 'CUR':
        # Current action
        # Loop through current action's values
        # Use action length to determine number of frames
        pass
    elif anim_export_mode == 'LNK':
        # Linked actions
        # Find all unique actions and export them same as in "current" setting
        pass
    elif anim_export_mode == 'TRA':
        # NLA tracks
        #
        pass
    elif anim_export_mode == 'SCN':
        # Full NLA animation
        # Use current scene, leave NLA track mutes/solos as is
        pass
    else:
        # Invalid option
        pass

    animation_bytes.extend(pack('B', len(animations)))
    for anim in animations:
        print(anim)

        # Remember state
        anim_data = rig_object.animation_data
        action_prev = anim_data.action
        mute_prev = [False] * len(anim_data.nla_tracks)
        for i, track in enumerate(anim_data.nla_tracks):
            mute_prev[i] = track.mute
            track.mute = True

        # Set animation (i.e. action)
        anim_data.action = anim

        # Determine keyframe times
        if   export_type == 'KFR':
            kf_times = sorted({p.co[0] for fcurve in anim_data.action.fcurves for p in fcurve.keyframe_points})
            kf_end = kf_times[len(kf_times)-1]
        elif export_type == 'SPL':
            kf_times = []
            for i in range(0, subdivisions+1):
                kf_times.append(anim.frame_range[0] + (anim.frame_range[1]-anim.frame_range[0])*i/subdivisions)
            kf_end = kf_times[subdivisions]
        else:
            # We shouldn't end up here
            pass

        #print(kf_times)

        # Play and write animation data
        if interpolation == "KFR":
            interpolation = 0
        if interpolation == "LIN":
            interpolation = 1
        if interpolation == "QAD":
            interpolation = 2

        write_animation_data(anim.name, context.scene, animation_bytes, rig_object, kf_times, kf_end, fps, interpolation)

        # Restore to previous state
        rig_object.animation_data.action = action_prev
        for i, track in enumerate(rig_object.animation_data.nla_tracks):
            track.mute = mute_prev[i]

    # Now build header
    header_bytes = bytearray("SMF_v11_by_Snidr_and_Bart\0", 'utf-8')

    tex_pos = len(header_bytes) + calcsize('IIIII')
    mod_pos = tex_pos + len(texture_bytes)
    rig_pos = mod_pos + len(model_bytes)
    ani_pos = rig_pos + len(rig_bytes)
    offsets = (tex_pos, mod_pos, rig_pos, ani_pos)
    header_bytes.extend(pack('I' * len(offsets), *offsets))

    placeholder_byte = 0
    header_bytes.extend(pack('I', placeholder_byte))

    # Write everything to file
    with open(filepath, "wb") as file:
        file.write(header_bytes)
        file.write(texture_bytes)
        file.write(model_bytes)
        file.write(rig_bytes)
        file.write(animation_bytes)

    return {'FINISHED'}

def fix_keyframe_dq(dq, frame_index, node_index):
    """Fix the keyframe DQ to make sure the animation doesn't look choppy"""
    if node_index > 0:
        pose_local_dq = dq_multiply(dq_get_conjugate(dq), dq)
        dq = dq_multiply(local_dq_conj, pose_local_dq)

        if frame_index == 0:
            if dq.real.w < 0:
                dq_negate(dq)
        else:
            if prevframe.real.dot(dq.real) < 0:
                dq_negate(dq)
    else:
        world_dq_conjugate = dq_get_conjugate(rig_dq)
        dq = dq_get_product(world_dq_conjugate, dq)

    return dq

def apply_world_matrix(matrix, matrix_world):
    """Applies the world matrix to the given bone matrix and makes sure scaling effects are ignored."""
    mat_w = matrix_world.copy()
    mat_w @= matrix

    # Decompose to get rid of scale
    deco = mat_w.decompose()
    mat_rot = deco[1].to_matrix()

    # Swap columns for use with SMF
    # Also add the translation
    temp = mat_rot.col[0][:]
    mat_rot.col[0] = mat_rot.col[1][:]
    mat_rot.col[1] = temp
    mat_w = mat_rot.to_4x4()
    mat_w.translation = deco[0][:]

    # Invert y values of the vectors
    # (i.e. mirror along Y to convert to SMF's left handed system)
    mat_w.row[1] *= -1

    return mat_w

def transform_matrix_to_smf(matrix):
    """"""
    # TODO Split up the two transforms properly (see apply_world_matrix)
    pass

def texture_image_from_node_tree(material):
    "Try to get a texture Image from the given material's node tree"
    if not material.use_nodes:
        return None

    output_node_list = [node for node in material.node_tree.nodes if node.type == 'OUTPUT_MATERIAL']
    if not output_node_list:
        return None

    node = output_node_list[0]
    if not node.inputs['Surface'].is_linked:
        return None

    node = node.inputs['Surface'].links[0].from_node
    if node.type == 'TEX_IMAGE' and node.image:
        # Directly connected texture image node with image set
        if node.image.has_data:
            return node.image
        else:
            """
            operator.report({'WARNING'}, (
            "Image " + node.image.name + " "
            "has no data loaded. Using default texture instead."
            ))
            return None
            """
    else:
        # Look a bit further
        # Try to generalize a bit by assuming texture input is at index 0
        # (color/texture inputs seem to connect to input 0 for all shaders)
        if not node.inputs[0].is_linked:
            return None

        node = node.inputs[0].links[0].from_node
        if node.type == 'TEX_IMAGE' and node.image:
            #if not(0 in node.image.size):
            if node.image.has_data:
                return node.image
            else:
                """
                operator.report({'WARNING'}, (
                "Image " + node.image.name + " "
                "has no data loaded. Using default texture instead."
                ))
                return None
                """
