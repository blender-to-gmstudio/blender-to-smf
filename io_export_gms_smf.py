import bpy
from struct import pack
from math import floor

# ExportHelper is a helper class, defines filename and
# invoke() function which calls the file selector.
from bpy_extras.io_utils import ExportHelper
from bpy.props import StringProperty, BoolProperty, EnumProperty
from bpy.types import Operator


class ExportSMF(Operator, ExportHelper):
    """This appears in the tooltip of the operator and in the generated docs"""
    bl_idname = "export_scene.smf"
    bl_label = "Export SMF"

    # ExportHelper mixin class uses this
    filename_ext = ".smf"

    filter_glob = StringProperty(
            default="*.smf",
            options={'HIDDEN'},
            maxlen=255,  # Max internal buffer length, longer would be clamped.
            )

    def execute(self, context):
        # Write textures/images (same thing as seen from SMF)
        texture_bytes = bytearray()
        texture_bytes.extend(pack('B', len(bpy.data.images)))       # Number of textures
        for tex in bpy.data.images:
            channels = tex.channels
            item_number = len(tex.pixels)
            pixel_number = int(len(tex.pixels)/channels)
            
            texture_bytes.extend(bytearray(tex.name + "\0",'utf-8'))# Texture name
            texture_bytes.extend(pack('HH',*tex.size[:]))           # Texture size (w,h)
            
            bytedata = [floor(component*255) for component in tex.pixels[:]]
            texture_bytes.extend(pack('B'*item_number,*bytedata))
        
        # Write materials
        material_bytes = bytearray()
        material_bytes.extend(pack('B', len(bpy.data.materials)))
        for mat in bpy.data.materials:
            material_bytes.extend(bytearray(mat.name + "\0", 'utf-8'))# Material name
            material_bytes.extend(pack('B',0))                        # Material type
        
        # Write models
        model_bytes = bytearray()
        for obj in [o for o in context.selected_objects if o.type=='MESH']:
            data = obj.data
            size = len(data.polygons) * 3 * 44
            
            model_bytes.extend(pack('I', size))
            # Write vertex buffer contents
            for face in data.polygons:
                for loop in [data.loops[i] for i in face.loop_indices]:
                    vert = data.vertices[loop.vertex_index]
                    model_bytes.extend(pack('fff', *(vert.co[:])))
                    model_bytes.extend(pack('fff', *(vert.normal[:])))
                    model_bytes.extend(pack('ff', *(0, 0)))           # uv
                    model_bytes.extend(pack('fff', *(loop.tangent[:])))
                    model_bytes.extend(pack('f', 0))
                    model_bytes.extend(pack('ffff', *(0, 0, 0, 0)))   # Bone indices (TODO)
                    model_bytes.extend(pack('ffff', *(0, 0, 0, 0)))   # Bone weights (TODO)
            
            # Mat and tex name
            mat_name = obj.material_slots[0].name
            model_bytes.extend(bytearray(mat_name + '\0','utf-8'))    # Mat name
            tex_name = obj.material_slots[0].material.texture_slots[0].texture.image.name
            model_bytes.extend(bytearray(tex_name + '\0', 'utf-8'))   # Tex name
            
            # Visible
            model_bytes.extend(pack('B',int(not obj.hide)))
            
            # Skinning info (dummy data)
            model_bytes.extend(pack('L',0))                           # n
        
        # Write (the absence of) nodes and ambient color
        node_bytes = bytearray()
        node_bytes.extend(pack('B',0))                                # nodeTypeNum
        node_bytes.extend(pack('B',0))                                # nodeNum
        
        ambient = [floor(component*255) for component in context.scene.world.ambient_color[:]]
        node_bytes.extend(pack('BBB',*ambient))
        
        # Write (the absence of a) collision buffer
        collision_buffer_bytes = bytearray()
        collision_buffer_bytes.extend(pack('L',0))                    # colBuffSize
        
        # Write (the absence of a) rig
        rig_bytes = bytearray()
        rig_bytes.extend(pack('B',0))                                 # boneNum
        
        # Write (the absence of) animation
        animation_bytes = bytearray()
        animation_bytes.extend(pack('B',0))                           # animationNum
        
        # Write (the absence of) saved selections
        saved_selections_bytes = bytearray()
        saved_selections_bytes.extend(pack('B',0))                    # selNum
        
        
        # Now build header
        version = 7
        header_bytes = bytearray("SnidrsModelFormat\0",'utf-8')
        header_bytes.extend(pack('f', version))
        
        header_size = 79
        
        offsets = (
            header_size,
            header_size + len(texture_bytes),
            header_size + len(texture_bytes) + len(material_bytes),
            header_size + len(texture_bytes) + len(material_bytes) + len(model_bytes),
            header_size + len(texture_bytes) + len(material_bytes) + len(model_bytes) + len(node_bytes),
            header_size + len(texture_bytes) + len(material_bytes) + len(model_bytes) + len(node_bytes) + len(collision_buffer_bytes),
            header_size + len(texture_bytes) + len(material_bytes) + len(model_bytes) + len(node_bytes) + len(collision_buffer_bytes) + len(rig_bytes),
            header_size + len(texture_bytes) + len(material_bytes) + len(model_bytes) + len(node_bytes) + len(collision_buffer_bytes) + len(rig_bytes) + len(animation_bytes)
        )
        header_bytes.extend(pack('IIIIIIII', *offsets))               # texPos, matPos, modPos, nodPos, colPos, rigPos, aniPos, selPos
        
        placeholder_bytes = (0, 0)
        header_bytes.extend(pack('II', *placeholder_bytes))
        
        no_models = len(context.selected_objects)
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
