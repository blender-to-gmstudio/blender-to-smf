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

    # List of operator properties, the attributes will be assigned
    # to the class instance from the operator settings before calling.
    use_setting = BoolProperty(
            name="Example Boolean",
            description="Example Tooltip",
            default=True,
            )

    type = EnumProperty(
            name="Example Enum",
            description="Choose between two items",
            items=(('OPT_A', "First Option", "Description one"),
                   ('OPT_B', "Second Option", "Description two")),
            default='OPT_A',
            )

    def execute(self, context):
        with open(self.filepath, "wb") as file:
            # Write header text
            file.write(bytearray("SnidrsModelFormat\0",'utf-8'))
            
            # Write version
            version = 7
            file.write(pack('f', version))
            
            # Write rest of header
            offsets = (0, 0, 0, 0, 0, 0, 0, 0)
            file.write(pack('IIIIIIII', *offsets))
            
            no_models = len(context.selected_objects)
            file.write(pack('B', no_models))
            
            placeholder_bytes = (0, 0)
            file.write(pack('II', *placeholder_bytes))
            
            center, size = (0, 0, 0), 1
            file.write(pack('ffff', *(*center, size)))
            
            # Write textures/images (same thing as seen from SMF)
            file.write(pack('B', len(bpy.data.images)))                 # Number of textures
            for tex in bpy.data.images:
                channels = tex.channels
                item_number = len(tex.pixels)
                pixel_number = int(len(tex.pixels)/channels)
                
                file.write(bytearray(tex.name + "\0",'utf-8'))          # Texture name
                file.write(pack('HH',*tex.size[:]))                     # Texture size (w,h)
                
                bytedata = [floor(component*255) for component in tex.pixels[:]]
                file.write(pack('B'*item_number,*bytedata))
            
            # Write materials
            file.write(pack('B', len(bpy.data.materials)))
            for mat in bpy.data.materials:
                file.write(bytearray(mat.name + "\0", 'utf-8'))         # Material name
                file.write(pack('B',0))                                 # Material type
            
            # Write models
            for obj in [o for o in context.selected_objects if o.type=='MESH']:
                data = obj.data
                size = len(data.polygons) * 3 * 44
                
                file.write(pack('I', size))
                # TODO Write vertex buffer contents here
                for face in data.polygons:
                    for loop in [data.loops[i] for i in face.loop_indices]:
                        vert = data.vertices[loop.vertex_index]
                        file.write(pack('fff', *(vert.co[:])))
                        file.write(pack('fff', *(vert.normal[:])))
                        file.write(pack('fff', *(loop.tangent[:])))
                        file.write(pack('f', 0))
                        file.write(pack('ffff', *(0, 0, 0, 0)))     # Bone indices (TODO)
                        file.write(pack('ffff', *(0, 0, 0, 0)))     # Bone weights (TODO)
                
                mat_name = obj.material_slots[0].name
                file.write(bytearray(mat_name + '\0','utf-8'))      # Mat name
                
                file.write(bytes(1))    # Null byte (end of texname)
                
                # TODO Skinning info (dummy data)
            
            # Write (the absence of) nodes
            file.write(pack('B',0))                                 # nodeTypeNum
            file.write(pack('B',0))                                 # nodeNum
            
            # Write ambient color
            ambient = [floor(component*255) for component in context.scene.world.ambient_color[:]]
            file.write(pack('BBB',*ambient))
            
            # Write (the absence of a) collision buffer
            file.write(pack('L',0))                                 # colBuffSize
            
            # Write (the absence of a) rig
            file.write(pack('U',0))                                 # boneNum
            
            # Write (the absence of) animation
            file.write(pack('B',0))                                 # animationNum
            
            # Write (the absence of) saved selections
            file.write(pack('B'),0))                                # selNum
        
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
