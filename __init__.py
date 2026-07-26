bl_info = {
    "name": "Export SMF",
    "description": "Export to SMF 12 (SnidrsModelFormat)",
    "author": "Bart Teunis",
    "version": (0, 9, 7),
    "blender": (2, 80, 0),
    "location": "File > Export",
    "warning": "",  # used for warning icon and text in addons panel
    "doc_url": "https://github.com/blender-to-gmstudio/blender-to-smf/wiki",
    "tracker_url": "https://github.com/blender-to-gmstudio/blender-to-smf/issues",
    "support": 'COMMUNITY',
    "category": "Import-Export"}

# Make sure to reload changes to code that we maintain ourselves
# when reloading scripts in Blender
if "bpy" in locals():
    import importlib
    if "export_smf" in locals():
        importlib.reload(export_smf)
    if "import_smf" in locals():
        importlib.reload(import_smf)

import bpy
from bpy.types import Operator
from bpy.props import (
    StringProperty,
    BoolProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
)
from bpy_extras.io_utils import (
    ExportHelper,
    ImportHelper,
)

from . import export_smf
from . import import_smf

from .export_smf import export_smf_file
from .import_smf import import_smf_file


class ImportSMF(Operator, ImportHelper):
    """Import an SMF 3D model"""
    bl_idname = "import_scene.smf"
    bl_label = "SMF (*.smf)"
    bl_options = {'REGISTER'}

    filename_ext = ".smf"

    filter_glob: StringProperty(
        default="*.smf",
        options={'HIDDEN'},
        maxlen=255,  # Max internal buffer length, longer would be clamped.
    )

    create_new_materials_images: BoolProperty(
        name="Create New Materials/Images",
        description= ("Force the creation of new materials and images, "
                      "even if materials/images with the same name already exist"),
        default=True,
    )

    def execute(self, context):
        keywords = self.as_keywords(ignore=("check_existing", "filter_glob", "ui_tab"))
        return import_smf_file(self, context, **keywords)


class ExportSMF(Operator, ExportHelper):
    """Export a selection of the current scene to SMF (SnidrsModelFormat)"""
    bl_idname = "export_scene.smf"
    bl_label = "SMF (*.smf)"
    bl_options = {'REGISTER', 'PRESET'}

    # ExportHelper mixin class uses this
    filename_ext = ".smf"

    filter_glob: StringProperty(
        default="*.smf",
        options={'HIDDEN'},
        maxlen=255,  # Max internal buffer length, longer would be clamped.
    )

    export_textures: BoolProperty(
        name="Export Textures",
        description="Whether textures should be exported with the model",
        default=True,
    )

    # "Advanced" export settings
    anim_export_mode: EnumProperty(
        name="What to export",
        description="How to export animations",
        items=[
            ("CUR", "Current Action", "Export the Armature's current action as a single animation", 0),
            ("LNK", "Linked NLA Actions", "Export all (unique) actions that are linked indirectly through NLA tracks", 1),
            #("TRA", "NLA Tracks", "Export every NLA track as a separate animation", 2),
            #("SCN", "Scene", "Export a single animation directly from the scene. This allows for the most advanced animations", 3),
        ],
        default="CUR",
    )
    anim_length_mode: EnumProperty(
        name="Animation Length",
        description="What value to use for the exported animation lengths",
        items=[
            ("SCN", "Scene", "Animation length equals scene length", 0),
            ("ACT", "Action", "Animation length equals action length", 1),
        ],
        default="SCN",
    )

    export_type: EnumProperty(
        name="Export Type",
        description="What to export",
        items=[
            ("KFR", "Keyframes", "Export the actual keyframes as defined in the animation", 0),
            ("SPL", "Samples", "Sample the animation at a given rate", 1),
        ],
        default="KFR",
    )

    multiplier: IntProperty(
        name="Sample Frame Multiplier",
        description=("Sample Frame Multiplier - Determines number of precomputed samples "
                     "using (number of keyframes) * (sample frame multiplier)"),
        default=4,
        soft_min=4,
        soft_max=20,
    )

    """
    normal_source: EnumProperty(
        name="Normal",
        description="The type of normal to export (vertex, loop, face)",
        items=[
            ("VERT", "Vertex", "Vertex normal", 0),
            ("LOOP", "Loop", "Loop normal", 1),
            ("FACE", "Face", "Face normal", 2),
        ],
        default="VERT",
    )
    """

    subdivisions: IntProperty(
        name="Subdivisions",
        description=("Number of times to subdivide an animation when exporting samples. "
                     "This subdivision is made for each animation individually."),
        default=10,
        soft_min=2,
    )

    scale: FloatProperty(
        name="Scale",
        description="Scale factor to be applied to geometry and rig",
        default=1,
        soft_min=.1,
    )

    interpolation: EnumProperty(
        name="Interpolation",
        description="The interpolation to use when playing the animations in SMF",
        items=[
            ("KFR", "Keyframe", "Use keyframe interpolation", 0),
            ("LIN", "Linear", "Sample the animation at a given rate", 1),
            ("QAD", "Quadratic", "Use quadratic interpolation", 2),
        ],
        default="LIN",
    )
    
    bone_influences: IntProperty(
        name="Bone Influences",
        description=("The number of bone influences to use"),
        default=4,
        min=1,
        max=4,
    )
    
    invert_uv_v: BoolProperty(
        name="Invert UV",
        description="Invert the v coordinate of uvs, i.e. export (u, 1 - v)",
        default=False,
    )
    
    # Whether to export the objects in the selected collection instead of the selection.
    # Only used with manual export.
    export_collection: BoolProperty(
        name="Export Selected Collection",
        description="Export objects in the selected collection instead of the selected objects.",
        default=False,
    )
    
    # Special property used by Collection export
    collection: StringProperty(
        name="Source Collection",
        description="Export only objects from this collection (and its children)",
        default="",
    )

    def execute(self, context):
        if self.export_collection:
            self.collection = bpy.context.collection.name if bpy.context.collection else ""
        
        keywords = self.as_keywords(ignore=("check_existing", "filter_glob", "ui_tab"))
        return export_smf_file(self, context, **keywords)

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False  # No animation.
        
        is_file_browser = context.space_data.type == 'FILE_BROWSER'
        
        export_panel_general(layout, self, is_file_browser)
        export_panel_advanced(layout, self, is_file_browser)


def export_panel_general(layout, operator, is_file_browser):
    header, body = layout.panel("SMF_export_general", default_closed=False)
    header.label(text="General")
    
    if body:
        body.prop(operator, 'export_textures')
        body.prop(operator, "invert_uv_v")
        
        if is_file_browser:
            body.prop(operator, 'export_collection')


def export_panel_advanced(layout, operator, is_file_browser):
    header, body = layout.panel("SMF_export_advanced", default_closed=True)
    header.label(text="Advanced")
    
    if body:
        body.prop(operator, 'anim_export_mode')
        #body.prop(operator, 'anim_length_mode')

        body.label(text="Sampling")
        body.prop(operator, 'export_type')
        if operator.export_type == 'SPL':
            body.prop(operator, 'subdivisions')
        
        body.label(text="Skinning")
        body.prop(operator, 'bone_influences')

        body.label(text="Other")
        #body.prop(operator, "normal_source")
        body.prop(operator, 'interpolation')
        body.prop(operator, 'multiplier')
        #body.prop(operator, "scale")


class IO_FH_smf(bpy.types.FileHandler):
    bl_idname = "IO_FH_smf"
    bl_label = "SMF"
    bl_export_operator = ExportSMF.bl_idname
    bl_file_extensions = ".smf"


def menu_func_export(self, context):
    self.layout.operator(ExportSMF.bl_idname, text="SMF (*.smf)")


def menu_func_import(self, context):
    self.layout.operator(ImportSMF.bl_idname, text="SMF (*.smf)")


classes = (
    ExportSMF,
    ImportSMF,  # Uncomment this to enable the WIP importer
    IO_FH_smf,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)


def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)


if __name__ == "__main__":
    register()
