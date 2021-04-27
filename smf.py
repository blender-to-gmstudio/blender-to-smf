# SMF export scripts for Blender
#
#from .pydq import dq_create_matrix_vector, dq_to_tuple_smf
import bpy
from struct import Struct, pack, calcsize
from mathutils import *
from math import *

SMF_version = 10
SMF_format_struct = Struct("ffffffffBBBBBBBBBBBB")
SMF_format_size = SMF_format_struct.size            # 44

### EXPORT ###

def rig_to_buffer():
    pass

def prep_mesh(obj, obj_rig, mesh):
    """Triangulate the given mesh using the BMesh library"""
    import bmesh
    
    bm = bmesh.new()
    bm.from_mesh(mesh)
    
    """
    geom_orig = bm.faces[:] + bm.verts[:] + bm.edges[:]
    # See https://blender.stackexchange.com/a/122321
    bmesh.ops.mirror(bm,
        geom=geom_orig,
        axis='Y',
        merge_dist=-1
    )
    bmesh.ops.delete(bm,geom=geom_orig,context='VERTS')
        matrix=Matrix(),
    bmesh.ops.recalc_face_normals(bm,faces= bm.faces[:])
    """
    
    # This makes sure the mesh is in the rig's coordinate system
    bmesh.ops.transform(bm, matrix=obj_rig.matrix_world, space=obj.matrix_world, verts=bm.verts[:])
    
    # Triangulate the mesh
    bmesh.ops.triangulate(bm, faces=bm.faces[:], quad_method='BEAUTY', ngon_method='BEAUTY')
    
    bm.to_mesh(mesh)
    bm.free()

def node_list(armature_object):
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

def export_smf(filepath, context, export_textures, export_nla_tracks, multiplier):
    """Main entry point for SMF export"""
    # Figure out what we're going to export
    object_list = context.selected_objects
    model_list = [o for o in object_list if o.type=='MESH']
    armature_list = [o for o in object_list if o.type=='ARMATURE']
    
    unique_materials = {slot.material for obj in model_list for slot in obj.material_slots if slot.material != None}
    
    # Check if we can export a valid rig
    # (supported are one or more connected hierarchies each with a single root bone in a single armature)
    rig_object = None
    rig = None
    anim = None
    if len(armature_list) > 0:
        rig_object = armature_list[0]
        rig = rig_object.data       # Export the first armature that we find
        if rig_object.animation_data:
            action = rig_object.animation_data.action
            if action:
                anim = action
        
        if len(armature_list) > 1:
            #self.report({'WARNING'},"More than one armature in selection. SMF supports one armature. The wrong armature may be exported.")
            pass
    
    texture_bytes = bytearray()
    
    # Write textures and their image data (same thing as seen from SMF)
    # Get unique images and keep their reference to the material that uses them
    unique_images = {}
    if export_textures:
        for mat in unique_materials:
            if not mat.use_nodes:
                continue
            
            output_node_list = [node for node in mat.node_tree.nodes if node.type == 'OUTPUT_MATERIAL']
            if len(output_node_list) == 0:
                continue
            
            node = output_node_list[0]
            if not node.inputs['Surface'].is_linked:
                continue
            
            node = node.inputs['Surface'].links[0].from_node
            if node.type == 'TEX_IMAGE':
                # Directly connected texture image node
                unique_images[mat.name] = node.image
            else:
                # Look a bit further
                # Try to generalize a bit by assuming texture input is at index 0
                # (color/texture inputs seem to connect to input 0 for all shaders)
                if not node.inputs[0].is_linked:
                    continue
                
                node = node.inputs[0].links[0].from_node
                if node.type == 'TEX_IMAGE':
                    unique_images[mat.name] = node.image
        
        texture_bytes.extend(pack('B', len(unique_images)))             # Number of unique images
        for img in unique_images.values():
            channels, item_number = img.channels, len(img.pixels)
            pixel_number = int(item_number/channels)
            pixel_data = img.pixels[:]                                  # https://blender.stackexchange.com/questions/3673/why-is-accessing-image-data-so-slow
            
            texture_bytes.extend(bytearray(img.name + "\0",'utf-8'))    # Texture name
            texture_bytes.extend(pack('HH',*img.size))                  # Texture size (w,h)
            
            print(img.name, img.size[:])
            
            bytedata = [floor(component*255) for component in pixel_data]
            texture_bytes.extend(pack('B'*item_number,*bytedata))
    else:
        texture_bytes.extend(pack('B', len(unique_images)))
    
    # Write an empty chunk for materials
    material_bytes = bytearray()
    material_bytes.extend(pack('B', len(unique_materials)))
    
    # Construct node list for SMF
    # (heads of disconnected bones need to become nodes, too)
    # TODO Check if we selected a rig!
    bones = node_list(rig_object)
    
    # Write rig
    rig_bytes = bytearray()
    
    if not rig:
        # No (valid) armature for export
        rig_bytes.extend(pack('B',0))
    else:
        rig_bytes.extend(pack('B',len(bones)))                      # nodeNum
        
        if len(rig.bones) == 0:
            #self.report({'WARNING'},"Armature has no bones. Exporting empty rig.")
            pass
        
        print("RIG")
        print("---")
        debug_rig = []
        debug_vals = []
        # Export all bones' tails => that's it!
        # Make sure to have a root bone!
        for n, bone in enumerate(bones):
            if bone:
                # This bone exists in the Blender rig
                b = bone
                
                parent_bone_index = 0 if not b.parent else bones.index(b.parent)
                connected = b.use_connect
                
                if b.parent and not b.use_connect:
                #if not b.use_connect:
                    # This is a node for which an added node has been written
                    parent_bone_index = n-1
                    connected = True
                    bones[parent_bone_index] = False            # This makes sure the "if bone" check keeps returning False!
                
                matrix = b.matrix_local.copy()
                matrix.translation = b.tail_local[:]
                
                name = b.name
            else:
                # This is one of the inserted nodes
                b = bones[n+1]
                
                parent_bone_index = 0 if not b.parent else bones.index(b.parent)
                connected = b.use_connect
                
                matrix = b.matrix_local.copy()
                matrix.translation = b.head_local[:]
                
                name = "Inserted for " + b.name
            
            # Add the world transform to the nodes, ignore scale
            mat_w = apply_world_matrix(matrix, rig_object.matrix_world)
            
            # Construct a list containing matrix values in the right order
            vals = [j for i in mat_w.transposed() for j in i]   # Convert to GM's matrix element order
            
            rig_bytes.extend(pack('f'*16, *vals))
            rig_bytes.extend(pack('B',parent_bone_index))       # node[@ eAnimNode.Parent]
            rig_bytes.extend(pack('B',connected))               # node[@ eAnimNode.IsBone]
            rig_bytes.extend(pack('B',False))                   # node[@ eAnimNode.Locked]
            rig_bytes.extend(pack('fff',*(0, 0, 0)))            # Primary IK axis (default all zeroes)
            
            t = mat_w.translation
            debug_rig.append((n, name, t[0], t[1], t[2], parent_bone_index, connected))
            debug_vals.append(str(["{0:.3f}".format(elem) for elem in vals]))
        
        # Print some extended, readable debug info
        print("SMF Node List")
        print("-------------")
        for i, d in enumerate(debug_rig):
            s = "{0:>4d} ({5:<3d}, {6:d}) - {1:<40} {2:<.3f} {3:<.3f} {4:<.3f}".format(*d)
            print(s)
            print(debug_vals[i])
    
    # Get the bindmap and relevant bone names
    bindmap = smf_bindmap(bones)
    bone_names = bindmap.keys()
    
    # Write models
    # TODO Apply modifiers, location, rotation and scale, etc.
    model_bytes = bytearray()
    no_models = len(model_list)
    model_bytes.extend(pack('B', no_models))
    for obj in model_list:
        # Create a triangulated copy of the mesh
        # that has everything applied (modifiers, transforms, etc.)
        mesh = obj.data.copy()
        prep_mesh(obj, rig_object, mesh)
        
        number_of_verts = 3 * len(mesh.polygons)
        size = number_of_verts * SMF_format_size
        
        # Precalculate skinning info
        #precalc_weights()
        print("SKINNING INFO")
        print("-------------")
        skin_indices = [None] * len(mesh.vertices)
        skin_weights = [None] * len(mesh.vertices)
        for i, v in enumerate(mesh.vertices):
            mod_groups = [group for group in v.groups if obj.vertex_groups[group.group].name in bone_names]
            groups = sorted(mod_groups, key=lambda group: group.weight)[0:4]
            s = sum([g.weight for g in groups])
            skin_indices[v.index] = [0,0,0,0]
            skin_weights[v.index] = [1,0,0,0]
            for index, group in enumerate(groups):              # 4 bone weights max!
                vg_index = group.group                          # Index of the vertex group
                vg_name = obj.vertex_groups[vg_index].name      # Name of the vertex group
                w = group.weight/s*255
                skin_indices[v.index][index] = bindmap[vg_name]
                skin_weights[v.index][index] = int(w if w <= 255 else 255)  # clamp to ubyte range!
            
            #print(v.index, indices[:], weights[:])
        
        model_bytes.extend(pack('I', size))
        # Write vertex buffer contents
        uv_data = mesh.uv_layers.active.data
        for face in mesh.polygons:
            for loop in [mesh.loops[i] for i in face.loop_indices]:
                vert = mesh.vertices[loop.vertex_index]
                model_bytes.extend(pack('fff', *(vert.co[:])))
                normal_source = vert                              # One of vert, loop, face
                normal = normal_source.normal
                model_bytes.extend(pack('fff', *(normal[:])))     # TODO correct normals (vertex, loop, polygon)!
                uv = uv_data[loop.index].uv
                model_bytes.extend(pack('ff', *(uv[:])))          # uv
                tan_int = [int(c*255) for c in loop.tangent]
                model_bytes.extend(pack('BBBB', *(*tan_int[:],0)))
                indices = skin_indices[vert.index]
                weights = skin_weights[vert.index]
                model_bytes.extend(pack('BBBB', *indices))        # Bone indices
                model_bytes.extend(pack('BBBB', *weights))        # Bone weights
                
                #vertex_bytedata = SMF_format_struct.pack()
                #model_bytes.extend(vertex_bytedata)
        
        # Mat and tex name
        mat_name = ""
        tex_name = ""
        if len(obj.material_slots) > 0:
            slot = obj.material_slots[0]
            if slot.material:
                mat = slot.material
                mat_name = mat.name
                if export_textures and mat_name in unique_images:
                    tex_name = unique_images[mat_name].name
        
        model_bytes.extend(bytearray(mat_name + '\0', 'utf-8'))   # Mat name
        model_bytes.extend(bytearray(tex_name + '\0', 'utf-8'))   # Tex name
        
        # Visible
        model_bytes.extend(pack('B',int(not obj.hide_viewport)))
        
        # Delete triangulated copy of the mesh
        bpy.data.meshes.remove(mesh)
    
    # Write animations
    animation_bytes = bytearray()
    
    def write_animation_data(name, scene, byte_data, rig_object, frame_indices, fps):
        """Writes all animation data to bytearray byte_data. Used to keep the code a bit tidy."""
        frame_number = len(frame_indices)
        animation_bytes.extend(bytearray(name + "\0", 'utf-8'))     # animName
        animation_bytes.extend(pack('B', True))                     # loop
        animation_bytes.extend(pack('f', frame_number/fps*1000))    # playTime (ms)
        animation_bytes.extend(pack('B', 1))                        # interpolation (0, 1, 2)
        animation_bytes.extend(pack('B', multiplier))               # sampleFrameMultiplier
        animation_bytes.extend(pack('I', frame_number))             # animFrameNumber
        
        # PRE Skeleton must be in Pose Position (see Armature.pose_position)
        frame_prev = scene.frame_current
        for frame in frame_indices:
            scene.frame_set(frame)
            
            kf_time = frame/frame_number
            
            byte_data.extend(pack('f', kf_time))
            
            print("Frame ", frame, " at time ", kf_time)
            
            # Loop through the armature's PoseBones using the bone/node order we got earlier
            # This guarantees a correct mapping of PoseBones to Bones
            #for rbone in rig_object.data.bones:
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
                vals = [j for i in mat_final.transposed() for j in i]   # Convert to GM's matrix element order
                byte_data.extend(pack('f'*16, *vals))
        
        # Restore frame position
        scene.frame_set(frame_prev)
    
    # Print the bindmap right here!
    print(bindmap)
    
    # Export each NLA track linked to the armature object as an animation
    # (use the first action's name as the animation name for now)
    print("ANIMATION")
    print("---------")
    
    # Common variables
    fps = context.scene.render.fps/context.scene.render.fps_base
    
    if export_nla_tracks:
        # Search for the presence of NLA tracks
        if rig_object.animation_data:
            if rig_object.animation_data.nla_tracks:
                # Clear the influence of the current action
                action = rig_object.animation_data.action
                rig_object.animation_data.action = None
                
                # We have NLA tracks
                tracks = rig_object.animation_data.nla_tracks
                animation_bytes.extend(pack('B', len(tracks)))                          # animNum
                
                for track in tracks:
                    # TODO Export entire tracks? Use track name instead?
                    print("Track ", track.name)
                    strips = track.strips
                    if len(strips) > 0:
                        # Use the first strip (assume only one per track for now)
                        strip = strips[0]
                        
                        print("Strips: ", len(strips))
                        print(strip.name)
                        
                        # Now play each track in solo and sample each animation
                        # Make sure to reset the frame in advance so the rig gets reset properly
                        context.scene.frame_set(context.scene.frame_start)
                        
                        is_solo_prev = track.is_solo
                        track.is_solo = True
                        
                        # TODO This needs a bit of work
                        # TODO keyframes <-> samples
                        frame_indices = range(int(strip.frame_start), int(strip.frame_end+1))
                        frame_max = int(strip.action_frame_end+1 - strip.action_frame_start)
                        write_animation_data(strip.name, context.scene, animation_bytes, rig_object, frame_indices, fps)
                        
                        track.is_solo = is_solo_prev
                    else:
                        # A bit of an issue here...
                        print("We're not supposed to be here...")
                        pass
                
                # Restore things
                rig_object.animation_data.action = action
    else:
        if not anim:
            # No valid animation
            animation_bytes.extend(pack('B', 0))                        # animNum
        else:
            # Single animation in armature object's action
            animation_bytes.extend(pack('B', 1))                        # animNum (one action)
            
            #keyframe_times = sorted({p.co[0] for fcurve in rig_object.animation_data.action.fcurves for p in fcurve.keyframe_points})
            frame_indices = range(context.scene.frame_start, context.scene.frame_end+1)
            frame_max = int(context.scene.frame_end - context.scene.frame_start)
            write_animation_data(anim.name, context.scene, animation_bytes, rig_object, frame_indices, fps)
    
    # Now build header
    header_bytes = bytearray("SMF_v10_by_Snidr_and_Bart\0", 'utf-8')
    
    tex_pos = len(header_bytes) + calcsize('IIIIII')
    mat_pos = tex_pos + len(texture_bytes)
    mod_pos = mat_pos + len(material_bytes)
    rig_pos = mod_pos + len(model_bytes)
    ani_pos = rig_pos + len(rig_bytes)
    offsets = (tex_pos, mat_pos, mod_pos, rig_pos, ani_pos)
    header_bytes.extend(pack('IIIII', *offsets))
    
    placeholder_byte = 0
    header_bytes.extend(pack('I', placeholder_byte))
    
    # Write everything to file
    with open(filepath, "wb") as file:
        file.write(header_bytes)
        file.write(texture_bytes)
        file.write(material_bytes)
        file.write(model_bytes)
        file.write(rig_bytes)
        file.write(animation_bytes)
    
    return {'FINISHED'}

def apply_world_matrix(matrix, matrix_world):
    """Applies the world matrix to the given bone matrix and makes sure scaling effects are ignored."""
    mat_w = matrix_world.copy()
    mat_w @= matrix
    deco = mat_w.decompose()
    mat_w = deco[1].to_matrix().to_4x4()
    mat_w.translation = deco[0][:]
    return mat_w

### IMPORT ###

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