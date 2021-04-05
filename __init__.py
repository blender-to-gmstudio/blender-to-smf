bl_info = {
    "name": "Export SMF",
    "description": "Export to SMF (SnidrsModelFormat)",
    "author": "Bart Teunis",
    "version": (0, 2, 0),
    "blender": (2, 82, 0),
    "location": "File > Export",
    "warning": "", # used for warning icon and text in addons panel
    "wiki_url": "https://github.com/blender-to-gmstudio/blender-to-smf/wiki",
    "category": "Import-Export"}

import bpy
from struct import pack
from mathutils import *
from math import *

from . import smf
from . import pydq

# ExportHelper is a helper class, defines filename and
# invoke() function which calls the file selector.
from bpy_extras.io_utils import ExportHelper, axis_conversion

from bpy.props import StringProperty, BoolProperty, EnumProperty
from bpy.types import Operator

def matrix_to_smf(matrix, translation):
    """Modifies the contents of a 4x4 mathutils.Matrix so that it can be used with SMF"""
    # Shuffle the columns to correspond to SMF
    # Column order [A, B, C, D] becomes [B, C, A, D]
    col0 = matrix.col[0][0:3]
    matrix.col[0][0:3] = matrix.col[1][0:3]
    matrix.col[1][0:3] = matrix.col[2][0:3]
    matrix.col[2][0:3] = col0
    
    # Overwrite the translation part by the one provided
    matrix.col[3][0:3] = translation[:]
    
    return matrix

class ExportSMF(Operator, ExportHelper):
    """Export a selection of the current scene to SMF (SnidrsModelFormat)"""
    bl_idname = "export_scene.smf"
    bl_label = "SMF (*.smf)"
    bl_options = {'REGISTER','PRESET'}

    # ExportHelper mixin class uses this
    filename_ext = ".smf"

    filter_glob : StringProperty(
            default="*.smf",
            options={'HIDDEN'},
            maxlen=255,  # Max internal buffer length, longer would be clamped.
            )
    
    export_textures : BoolProperty(
            name="Export Textures",
            description="Whether textures should be exported with the model",
            default=False,
            )
    
    export_nla_tracks : BoolProperty(
            name="Export NLA Tracks",
            description="Whether to export multiple animations on all NLA tracks that are linked to this model (Experimental)",
            default=False,
    )
    
    @staticmethod
    def prepare_mesh(mesh):
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
            matrix=Matrix(),
            merge_dist=-1
        )
        bmesh.ops.delete(bm,geom=geom_orig,context='VERTS')
        bmesh.ops.recalc_face_normals(bm,faces= bm.faces[:])
        """
        
        bmesh.ops.triangulate(bm, faces=bm.faces[:], quad_method='BEAUTY', ngon_method='BEAUTY')
        
        bm.to_mesh(mesh)
        bm.free()

    def execute(self, context):
        # Constants initialization, etc.
        SMF_version = 7
        SMF_format_size = 44
        SMF_header_size = 79
        
        # Figure out what we're going to export
        object_list = context.selected_objects
        model_list = [o for o in object_list if o.type=='MESH']
        armature_list = [o for o in object_list if o.type=='ARMATURE']
        
        # Check if we can export a valid rig
        # (supported are one or more connected hierarchies each with a single root bone in a single armature)
        rig_object = None
        rig = None
        anim = None
        if len(armature_list) > 0:
            rig_object = armature_list[0]
            rig = rig_object.data       # Export the first armature that we find
            anim = rig_object.animation_data.action
            
            unsupported_rig = len([bone for bone in rig.bones if bone.parent != None and bone.use_connect == False]) > 0
            if unsupported_rig:
                rig_object = None
                rig = None
                anim = None
                self.report({'WARNING'},"The currently selected rig contains disconnected bones, which are not supported by SMF. Export of armature will be skipped.")
            
            if len(armature_list) > 1:
                self.report({'WARNING'},"More than one armature in selection. SMF supports one armature. The wrong armature may be exported.")
        
        texture_bytes = bytearray()
        material_bytes = bytearray()
        
        if self.export_textures:
            # Write textures and their image data (same thing as seen from SMF)
            unique_materials = {slot.material for obj in model_list for slot in obj.material_slots if slot.material != None}
            unique_textures = {slot.texture for mat in unique_materials for slot in mat.texture_slots if slot != None}
            #unique_images = {}
            
            texture_bytes.extend(pack('B', len(unique_textures)))       # Number of textures
            for tex in unique_textures:
                img = tex.image
                channels, item_number = img.channels, len(img.pixels)
                pixel_number = int(item_number/channels)
                
                texture_bytes.extend(bytearray(tex.name + "\0",'utf-8'))# Texture name
                texture_bytes.extend(pack('HH',*img.size))              # Texture size (w,h)
                
                bytedata = [floor(component*255) for component in img.pixels[:]]
                texture_bytes.extend(pack('B'*item_number,*bytedata))
            
            # Write materials
            material_bytes.extend(pack('B', len(unique_materials)))
            for mat in unique_materials:
                # Determine SMF material type
                if mat.use_shadeless:
                    mat_type = 0
                else:
                    mat_type = 2                                              # Per-fragment shading
                
                # Basic info for all material types
                material_bytes.extend(bytearray(mat.name + "\0", 'utf-8'))    # Material name
                material_bytes.extend(pack('B',mat_type))                     # Material type
                
                if mat_type > 0:
                    # Effect modifiers
                    spec_int = int(mat.specular_intensity*127)
                    material_bytes.extend(pack('B',spec_int))                 # SpecReflectance
                    material_bytes.extend(pack('B',mat.specular_hardness))    # SpecDamping
                    material_bytes.extend(pack('B',1))                        # CelSteps
                    material_bytes.extend(pack('B',0))                        # RimPower
                    material_bytes.extend(pack('B',0))                        # RimFactor
                    
                    # Normal map
                    material_bytes.extend(pack('B',0))                        # Not enabled right now
                    
                    # Outlines
                    material_bytes.extend(pack('B',0))                        # Not enabled right now
                    
                    # Reflection
                    material_bytes.extend(pack('B',0))                        # Not enabled right now
        else:
            material_bytes.extend(pack('B', 0))                         # No materials
            texture_bytes.extend(pack('B', 0))                          # No textures
        
        # Write models
        # TODO Apply modifiers, location, rotation and scale, etc.
        model_bytes = bytearray()
        for obj in model_list:
            mesh = obj.data.copy()
            ExportSMF.prepare_mesh(mesh)
            
            number_of_verts = 3 * len(mesh.polygons)
            size = number_of_verts * SMF_format_size
            
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
                    indices, weights = [0,0,0,0], [0,0,0,0]
                    for index,group in enumerate(vert.groups[0:4]):   # 4 bone weights max!
                        indices[index] = group.group
                        w = group.weight*255
                        weights[index] = int(w if w <= 255 else 255)  # clamp to ubyte range!
                    model_bytes.extend(pack('BBBB', *indices))        # Bone indices
                    #print(weights)
                    model_bytes.extend(pack('BBBB', *weights))        # Bone weights
            
            # Mat and tex name
            mat_name = ""
            tex_name = ""
            if len(obj.material_slots) > 0:
                slot = obj.material_slots[0]
                if slot.material:
                    mat = slot.material
                    mat_name = mat.name
                    #if mat.texture_slots[0] != None:
                    #    tex = mat.texture_slots[0].texture
                    #tex_name = tex.name
            
            model_bytes.extend(bytearray(mat_name + '\0', 'utf-8'))   # Mat name
            model_bytes.extend(bytearray(tex_name + '\0', 'utf-8'))   # Tex name
            
            # Visible
            model_bytes.extend(pack('B',int(not obj.hide_viewport)))
            
            # Skinning info (dummy data)
            model_bytes.extend(pack('L',0))                           # n
            model_bytes.extend(pack('L',0))                           # n (#2)
            
            # Delete triangulated copy of the mesh
            bpy.data.meshes.remove(mesh)
        
        # Write (the absence of) nodes and ambient color
        #node_types = {'MESH','CAMERA','LAMP','EMPTY','SPEAKER','CURVE'}
        node_types = {}
        
        node_bytes = bytearray()
        node_bytes.extend(pack('B',len(node_types)))                  # nodeTypeNum
        for node_type in node_types:
            node_bytes.extend(bytearray(node_type,'utf-8'))           # node name
            node_bytes.extend(pack('B',0))                            # empty string
            node_bytes.extend(pack('f',1))                            # node scale
        
        node_bytes.extend(pack('B',0))                                # nodeNum
        
        ambient = [floor(component*255) for component in context.scene.world.color[:]]
        node_bytes.extend(pack('BBB',*ambient))
        
        # Write (the absence of a) collision buffer
        collision_buffer_bytes = bytearray()
        collision_buffer_bytes.extend(pack('L', 0))                   # colBuffSize
        
        # Write rig
        rig_bytes = bytearray()
        rig_dqs = {}
        
        if not rig:
            # No (valid) armature for export
            rig_bytes.extend(pack('B',0))
        else:
            rig_bytes.extend(pack('B',len(rig.bones)))            # nodeNum
            
            if len(rig.bones) == 0:
                self.report({'WARNING'},"Armature has no bones. Exporting empty rig.")
            
            print("RIG")
            print("---")
            # Export all bones' tails => that's it!
            # Make sure to have a root bone!
            for bone in rig.bones:
                parent_bone_index = 0 if bone.parent == None else rig.bones.find(bone.parent.name)
                connected = 0 if bone.parent == None else 1
                
                # Create a matrix, useable by SMF, from the 3x3 bone matrix and the bone's tail
                mat = matrix_to_smf(bone.matrix.to_4x4(), bone.tail)
                
                # Create a DQ and convert to a tuple that can be written directly
                dq = pydq.dq_create_matrix(mat)
                dq_values = pydq.dq_to_tuple_smf(dq)
                
                print(bone.name)
                print(mat)
                print(dq)
                print(dq_values)
                
                rig_bytes.extend(pack('ffffffff', *dq_values))
                rig_bytes.extend(pack('B',parent_bone_index))
                rig_bytes.extend(pack('B',connected))             # Determines SMF parent bone behaviour
        
                                                                  # (root/detached from parent or not)
        # Write animations
        animation_bytes = bytearray()
        
        def write_animation_data(context, byte_data, rig_object, frame_indices):
            """Writes all animation data to bytearray byte_data. Used to keep the code a bit tidy."""
            # PRE Skeleton must be in Pose Position (see Armature.pose_position)
            frame_prev = context.scene.frame_current
            for frame in frame_indices:
                context.scene.frame_set(frame)
                
                kf_time = frame/21 # Yuck! Hard-coded test value!
                
                byte_data.extend(pack('f', kf_time))
                
                print("Frame ", frame, " at time ", kf_time)
                
                # Loop through the armature's PoseBones using its Bone order (!)
                # This guarantees a correct mapping of PoseBones to Bones
                for rbone in rig_object.data.bones:
                    # Get the bone (The name is identical (!))
                    bone = rig_object.pose.bones[rbone.name]
                    
                    # Use matrix_basis here
                    mat = bone.matrix_basis.copy()
                    mat = matrix_to_smf(mat, bone.tail)
                    
                    par = bone.parent if bone.parent else rig_object.pose.bones[0]
                    mat_parent = par.matrix_basis.copy()
                    mat_parent = matrix_to_smf(mat, par.tail)
                    
                    # Create DQs and do some DQ math
                    # poseLocalDQ = dq_multiply(dq_get_conjugate(poseDQ[node[eAnimNode.Parent]]), poseDQ[i]);
                    dq = pydq.dq_create_matrix(mat)
                    dq_parent = pydq.dq_create_matrix(mat_parent)
                    dq_parent_conj = pydq.dq_get_conjugate(dq_parent)
                    dq = pydq.dq_get_product(dq_parent_conj, dq)
                    
                    vals = pydq.dq_to_tuple_smf(dq)
                    
                    #vals = [j for i in mat.transposed() for j in i] # Convert to GM's matrix element order
                    
                    print(bone.name)
                    print("SMF matrix: ")
                    print(mat)
                    print("DQ value: ")
                    print(dq)
                    print("Buffer values written: ")
                    print(dq_values)
                    
                    byte_data.extend(pack('ffffffff', *vals))
            
            # Restore frame position
            context.scene.frame_set(frame_prev)
        
        # Export each NLA track linked to the armature object as an animation
        # (use the first action's name as the animation name for now)
        print("ANIMATION")
        print("---------")
        if self.export_nla_tracks:
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
                        print("Track ", track.name)
                        strips = track.strips
                        if len(strips) > 0:
                            print("Strips: ", len(strips))
                            strip = strips[0]
                            print(strip.name)
                            
                            # Now play each track in solo and sample each animation
                            # Make sure to reset the frame in advance so the rig gets reset properly
                            context.scene.frame_set(context.scene.frame_start)
                            
                            track.is_solo = True
                            
                            frame_indices = range(int(strip.action_frame_start), int(strip.action_frame_end+1))
                            frame_max = int(strip.action_frame_end+1 - strip.action_frame_start)
                            animation_bytes.extend(bytearray(strip.name + "\0", 'utf-8'))   # animName
                            animation_bytes.extend(pack('B', frame_max))                    # animFrameNumber
                            
                            write_animation_data(context, animation_bytes, rig_object, frame_indices)
                            
                            track.is_solo = False
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
                
                frame_indices = range(context.scene.frame_start, context.scene.frame_end+1)
                frame_max = int(context.scene.frame_end - context.scene.frame_start)
                animation_bytes.extend(bytearray(anim.name + "\0", 'utf-8'))# animName
                animation_bytes.extend(pack('B', frame_max))                # animFrameNumber
                
                write_animation_data(context, animation_bytes, rig_object, frame_indices)
        
        # Write (the absence of) saved selections
        saved_selections_bytes = bytearray()
        saved_selections_bytes.extend(pack('B', 0))                     # selNum
        
        # Now build header
        header_bytes = bytearray("SnidrsModelFormat\0", 'utf-8')
        header_bytes.extend(pack('f', SMF_version))
        
        tex_pos = SMF_header_size
        mat_pos = tex_pos + len(texture_bytes)
        mod_pos = mat_pos + len(material_bytes)
        nod_pos = mod_pos + len(model_bytes)
        col_pos = nod_pos + len(node_bytes)
        rig_pos = col_pos + len(collision_buffer_bytes)
        ani_pos = rig_pos + len(rig_bytes)
        sel_pos = ani_pos + len(animation_bytes)
        offsets = (tex_pos,mat_pos,mod_pos,nod_pos,col_pos,rig_pos,ani_pos,sel_pos)
        header_bytes.extend(pack('IIIIIIII', *offsets))               # texPos, matPos, modPos, nodPos, colPos, rigPos, aniPos, selPos
        
        placeholder_bytes = (0, 0)
        header_bytes.extend(pack('II', *placeholder_bytes))
        
        no_models = len(model_list)
        header_bytes.extend(pack('B', no_models))
        
        center, size = (0, 0, 0), 1
        header_bytes.extend(pack('ffff', *(*center, size)))
        
        header_size = len(header_bytes)
        #print(header_size)
        
        # Write everything to file
        with open(self.filepath, "wb") as file:
            file.write(header_bytes)
            file.write(texture_bytes)
            file.write(material_bytes)
            file.write(model_bytes)
            file.write(node_bytes)
            file.write(collision_buffer_bytes)
            file.write(rig_bytes)
            file.write(animation_bytes)
            file.write(saved_selections_bytes)
        
        return {'FINISHED'}


# Only needed if you want to add into a dynamic menu
def menu_func_export(self, context):
    self.layout.operator(ExportSMF.bl_idname, text="SMF (*.smf)")


def register():
    bpy.utils.register_class(ExportSMF)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)


def unregister():
    bpy.utils.unregister_class(ExportSMF)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)


if __name__ == "__main__":
    register()
