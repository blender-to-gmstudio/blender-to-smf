import bpy
from struct import pack
from math import floor
from mathutils import Quaternion

# ExportHelper is a helper class, defines filename and
# invoke() function which calls the file selector.
from bpy_extras.io_utils import ExportHelper
from bpy.props import StringProperty, BoolProperty, EnumProperty
from bpy.types import Operator


class ExportSMF(Operator, ExportHelper):
    """This appears in the tooltip of the operator and in the generated docs"""
    bl_idname = "export_scene.smf"
    bl_label = "Export SMF"
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
        

    def execute(self, context):
        # Write textures and their image data (same thing as seen from SMF)
        # TODO Only export textures that are in use by the model
        #      (instead of everything in bpy.data)
        texture_bytes = bytearray()
        texture_bytes.extend(pack('B', len(bpy.data.textures)))     # Number of textures
        for tex in bpy.data.textures:
            img = tex.image
            channels, item_number = img.channels, len(img.pixels)
            pixel_number = int(item_number/channels)
            
            texture_bytes.extend(bytearray(tex.name + "\0",'utf-8'))# Texture name
            texture_bytes.extend(pack('HH',*img.size[:]))           # Texture size (w,h)
            
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
        # TODO triangulate meshes! (don't forget to do this!)
        model_bytes = bytearray()
        model_list = [o for o in context.selected_objects if o.type=='MESH']
        for obj in model_list:
            mesh = obj.data.copy()
            ExportSMF.triangulate_mesh(mesh)
            
            size = len(mesh.polygons) * 3 * 44                            # 44 = size in bytes of vertex format
            
            model_bytes.extend(pack('I', size))
            # Write vertex buffer contents
            uv_data = mesh.uv_layers.active.data
            for face in mesh.polygons:
                for loop in [mesh.loops[i] for i in face.loop_indices]:
                    vert = mesh.vertices[loop.vertex_index]
                    model_bytes.extend(pack('fff', *(vert.co[:])))
                    model_bytes.extend(pack('fff', *(vert.normal[:])))
                    uv = uv_data[loop.index].uv
                    model_bytes.extend(pack('ff', *uv))               # uv
                    tan_int = [int(c*255) for c in loop.tangent]
                    model_bytes.extend(pack('BBBB', *(*tan_int[:],0)))
                    model_bytes.extend(pack('BBBB', *(0, 0, 0, 0)))   # Bone indices (TODO)
                    model_bytes.extend(pack('BBBB', *(0, 0, 0, 0)))   # Bone weights (TODO)
            
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
        node_types = {'MESH','CAMERA','LAMP','EMPTY','SPEAKER','CURVE'}
        
        node_bytes = bytearray()
        #node_bytes.extend(pack('B',len(node_types)))                  # nodeTypeNum
        #node_bytes.extend(pack('B',len(context.selected_objects)))    # nodeNum
        
        node_bytes.extend(pack('B',0))                                # nodeTypeNum
        node_bytes.extend(pack('B',0))                                # nodeNum
        
        ambient = [floor(component*255) for component in context.scene.world.ambient_color[:]]
        node_bytes.extend(pack('BBB',*ambient))
        
        # Write (the absence of a) collision buffer
        collision_buffer_bytes = bytearray()
        collision_buffer_bytes.extend(pack('L',0))                    # colBuffSize
        
        # Write rig
        # TODO Is this the pose mode we're writing here??
        rig = bpy.data.armatures[0]                                   # Happily assume there's a rig at index 0...
        
        rig_bytes = bytearray()
        rig_bytes.extend(pack('B',len(rig.bones)))                    # boneNum
        for bone in rig.bones:
            dual_quaternion = (0,0,0,0,0,0,0,0)
            # Qr = r; Qd = .5 * (0, t) * r
            head = bone.head
            Qr = bone.matrix.to_quaternion()
            Qd = .5 * Quaternion([0, *bone.head[:]]) * Qr
            rig_bytes.extend(pack('ffffffff',*[*Qr[:],*Qd[:]]))       # Something like this perhaps??
            if bone.parent == None:
                parent_bone_index = 0                                 # Is this assumption correct??
            else:
                parent_bone_index = rig.bones.find(bone.parent.name) + 1
            rig_bytes.extend(pack('B',parent_bone_index))
            rig_bytes.extend(pack('B',bone.use_connect))              # Attached to parent bone?
        
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
        version = 7
        header_bytes = bytearray("SnidrsModelFormat\0",'utf-8')
        header_bytes.extend(pack('f', version))
        
        header_size = 79
        
        tex_pos = header_size
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
