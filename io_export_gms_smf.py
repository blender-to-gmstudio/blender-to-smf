bl_info = {
    "name": "Export SMF",
    "description": "Export to SMF (SnidrsModelFormat)",
    "author": "Bart Teunis",
    "version": (0, 2, 0),
    "blender": (2, 79, 0),
    "location": "File > Export",
    "warning": "", # used for warning icon and text in addons panel
    "wiki_url": "",
    "category": "Import-Export"}

import bpy
from struct import pack
from mathutils import *
from math import *

# ExportHelper is a helper class, defines filename and
# invoke() function which calls the file selector.
from bpy_extras.io_utils import ExportHelper

from bpy.props import StringProperty, BoolProperty, EnumProperty
from bpy.types import Operator


class ExportSMF(Operator, ExportHelper):
    """Export a selection of the current scene to SMF (SnidrsModelFormat)"""
    bl_idname = "export_scene.smf"
    bl_label = "SMF (*.smf)"
    bl_options = {'REGISTER','PRESET'}

    # ExportHelper mixin class uses this
    filename_ext = ".smf"

    filter_glob = StringProperty(
            default="*.smf",
            options={'HIDDEN'},
            maxlen=255,  # Max internal buffer length, longer would be clamped.
            )
    
    @staticmethod
    def triangulate_mesh(mesh):
        """Triangulate the given mesh using the BMesh library"""
        import bmesh
        
        bm = bmesh.new()
        bm.from_mesh(mesh)
        
        bmesh.ops.triangulate(bm, faces=bm.faces[:], quad_method=0, ngon_method=0)
        
        bm.to_mesh(mesh)
        bm.free()
    
    @staticmethod
    def dual_quaternion(rotation_matrix,vector):
        """Creates a tuple containing the dual quaternion components out of a rotation matrix and translation vector"""
        vector = [vector[0],vector[1],vector[2]]        # Offset
        #Qr = rotation_matrix.to_quaternion()            # Rotation axis & angle as quaternion
        Qr = Matrix().to_quaternion()            # Rotation axis & angle as quaternion
        Qd = .5 * Quaternion([0, *vector[:]]) * Qr
        Qr.x = -Qr.x
        Qr.z = -Qr.z
        Qd.x = -Qd.x
        Qd.z = -Qd.z
        return (*Qr[:], *Qd[:])

    def execute(self, context):
        # Constants initialization, etc.
        SMF_version = 7
        SMF_format_size = 44
        SMF_header_size = 79
        
        object_list = context.selected_objects
        model_list = [o for o in object_list if o.type=='MESH']
        armature_list = [o for o in object_list if o.type=='ARMATURE']
        if (len(armature_list) > 1):
            report({'WARNING'},"More than one armature in selection. SMF supports one armature. The wrong armature may be exported.")
        
        # Write textures and their image data (same thing as seen from SMF)
        # TODO Only export textures that are in use by the model(s)
        #      (instead of everything in bpy.data)
        texture_bytes = bytearray()
        texture_bytes.extend(pack('B', len(bpy.data.textures)))     # Number of textures
        for tex in bpy.data.textures:
            img = tex.image
            channels, item_number = img.channels, len(img.pixels)
            pixel_number = int(item_number/channels)
            
            texture_bytes.extend(bytearray(tex.name + "\0",'utf-8'))# Texture name
            texture_bytes.extend(pack('HH',*img.size))              # Texture size (w,h)
            
            bytedata = [floor(component*255) for component in img.pixels[:]]
            texture_bytes.extend(pack('B'*item_number,*bytedata))
        
        # Write materials
        # TODO Support more complex materials (types != 0)
        material_bytes = bytearray()
        material_bytes.extend(pack('B', len(bpy.data.materials)))
        for mat in bpy.data.materials:
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
                
            
        # Write models
        # TODO Apply modifiers, location, rotation and scale, etc.
        # TODO Flip normals, now that we flip y coordinate
        # TODO Invert y
        model_bytes = bytearray()
        for obj in model_list:
            mesh = obj.data.copy()
            ExportSMF.triangulate_mesh(mesh)
            
            number_of_verts = 3 * len(mesh.polygons)
            size = number_of_verts * SMF_format_size
            
            model_bytes.extend(pack('I', size))
            # Write vertex buffer contents
            uv_data = mesh.uv_layers.active.data
            for face in mesh.polygons:
                for loop in [mesh.loops[i] for i in face.loop_indices]:
                    vert = mesh.vertices[loop.vertex_index]
                    co = [vert.co.x,-vert.co.y,vert.co.z]
                    model_bytes.extend(pack('fff', *(co[:])))
                    normal_source = vert                              # One of vert, loop, face
                    normal = [normal_source.normal.x,-normal_source.normal.y,normal_source.normal.z]
                    model_bytes.extend(pack('fff', *(normal[:])))     # TODO correct normals (vertex, loop, polygon)!
                    uv = uv_data[loop.index].uv
                    model_bytes.extend(pack('ff', *[uv[0],-uv[1]]))   # uv
                    tan_int = [int(c*255) for c in loop.tangent]
                    model_bytes.extend(pack('BBBB', *(*tan_int[:],0)))
                    indices = [0,0,0,0]
                    weights = [0,0,0,0]
                    for index,group in enumerate(vert.groups[0:4]):   # 4 bone weights max!
                        indices[index] = group.group
                        weights[index] = int(group.weight*255)
                    model_bytes.extend(pack('BBBB', *indices))        # Bone indices
                    model_bytes.extend(pack('BBBB', *weights))        # Bone weights
            
            # Mat and tex name
            mat_name = obj.material_slots[0].name
            model_bytes.extend(bytearray(mat_name + '\0','utf-8'))    # Mat name
            tex_name = obj.material_slots[0].material.texture_slots[0].texture.name
            model_bytes.extend(bytearray(tex_name + '\0', 'utf-8'))   # Tex name
            
            # Visible
            model_bytes.extend(pack('B',int(not obj.hide)))
            
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
        
        ambient = [floor(component*255) for component in context.scene.world.ambient_color[:]]
        node_bytes.extend(pack('BBB',*ambient))
        
        # Write (the absence of a) collision buffer
        collision_buffer_bytes = bytearray()
        collision_buffer_bytes.extend(pack('L',0))                    # colBuffSize
        
        # Write rig
        rig_bytes = bytearray()
        
        if len(armature_list) > 0:
            rig = armature_list[0].data                               # First armature in selection
            rig_bytes.extend(pack('B',len(rig.bones)+1))              # boneNum
            
            if len(rig.bones) > 0:
                # Write all nodes, except the last one
                for bone in rig.bones:
                    dq = ExportSMF.dual_quaternion(bone.matrix_local,bone.head_local)
                    parent_bone_index = 0 if bone.parent == None else rig.bones.find(bone.parent.name)
                    
                    rig_bytes.extend(pack('ffffffff',*dq))
                    rig_bytes.extend(pack('B',parent_bone_index))
                    rig_bytes.extend(pack('B',bone.use_connect))      # Determines SMF parent bone behaviour
                                                                      # (root/detached from parent or not)
                    print(parent_bone_index)
                    print(bone.use_connect)
                
                # Write tail of last bone as final node
                ind = len(rig.bones)-1
                bone = rig.bones[ind]
                dq = ExportSMF.dual_quaternion(bone.matrix_local,bone.tail_local)
                rig_bytes.extend(pack('ffffffff',*dq))
                parent_bone_index = rig.bones.find(bone.name)         # We count nodes, not bones (!)
                #parent_bone_index = 0 if bone.parent == None else rig.bones.find(bone.parent.name)
                rig_bytes.extend(pack('B',parent_bone_index))
                rig_bytes.extend(pack('B',bone.use_connect))
        else:
            rig_bytes.extend(pack('B',0))                             # No rig => no bones
        
        # Write animations (a first quick attempt)
        animation_bytes = bytearray()
        animation_bytes.extend(pack('B',0))                           # animationNum
        
        #animation_bytes = bytearray()
        #animation_bytes.extend(pack('B',len(bpy.data.actions))        # animationNum
        #for action in bpy.data.actions:
        #    animation_bytes.extend(bytearray(action.name+"\0",'utf-8')# animation name
        #    #for frame in action.frame_range:
        #    #    pass
        
        # Write (the absence of) saved selections
        saved_selections_bytes = bytearray()
        saved_selections_bytes.extend(pack('B',0))                    # selNum
        
        
        # Now build header
        header_bytes = bytearray("SnidrsModelFormat\0",'utf-8')
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
    self.layout.operator(ExportSMF.bl_idname, text="Export SMF")


def register():
    bpy.utils.register_class(ExportSMF)
    bpy.types.INFO_MT_file_export.append(menu_func_export)


def unregister():
    bpy.utils.unregister_class(ExportSMF)
    bpy.types.INFO_MT_file_export.remove(menu_func_export)


if __name__ == "__main__":
    register()

    # test call
    bpy.ops.export_scene.smf('INVOKE_DEFAULT')
