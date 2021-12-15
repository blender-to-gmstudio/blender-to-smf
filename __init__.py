bl_info = {
    "name": "Export SMF",
    "description": "Export to SMF 10 (SnidrsModelFormat)",
    "author": "Bart Teunis",
    "version": (0, 8, 0),
    "blender": (2, 80, 0),
    "location": "File > Export",
    "warning": "", # used for warning icon and text in addons panel
    "wiki_url": "https://github.com/blender-to-gmstudio/blender-to-smf/wiki",
    "tracker_url": "https://github.com/blender-to-gmstudio/blender-to-smf/issues",
    "category": "Import-Export"}

import bpy
from .export_smf import export_smf
from .import_smf import import_smf

# ExportHelper is a helper class, defines filename and
# invoke() function which calls the file selector.
from bpy_extras.io_utils import ExportHelper, ImportHelper

from bpy.props import StringProperty, BoolProperty, EnumProperty, FloatProperty, IntProperty
from bpy.types import Operator

class ImportSMF(Operator, ImportHelper):
    """Import an SMF 3D model"""
    bl_idname="import_scene.smf"
    bl_label = "SMF (*.smf)"
    bl_options = {'REGISTER'}

    filename_ext = ".smf"

    filter_glob: StringProperty(
        default="*.smf",
        options={'HIDDEN'},
        maxlen=255,  # Max internal buffer length, longer would be clamped.
    )

    def execute(self, context):
        return import_smf(self.filepath)

class ExportSMF(Operator, ExportHelper):
    """Export a selection of the current scene to SMF (SnidrsModelFormat)"""
    bl_idname = "export_scene.smf"
    bl_label = "SMF (*.smf)"
    bl_options = {'REGISTER', 'PRESET'}

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
        default=True,
    )

    # "Advanced" export settings
    anim_export_mode : EnumProperty(
        name="What to export",
        description="How to export animations",
        items=[
            ("CUR","Current Action", "Export the Armature's current action as a single animation", 0),
            ("LNK","Linked NLA Actions", "Export all (unique) actions that are linked indirectly through NLA tracks", 1),
            ("TRA","NLA Tracks", "Export every NLA track as a separate animation", 2),
            ("SCN","Scene", "Export a single animation directly from the scene. This allows for the most advanced animations", 3),
        ],
        default="CUR",
    )
    anim_length_mode : EnumProperty(
        name="Animation Length",
        description="What value to use for the exported animation lengths",
        items=[
            ("SCN", "Scene", "Animation length equals scene length", 0),
            ("ACT", "Action", "Animation length equals action length", 1),
        ],
        default="SCN",
    )

    export_type : EnumProperty(
        name="Export Type",
        description="What to export",
        items=[
            ("KFR", "Keyframes", "Export the actual keyframes as defined in the animation", 0),
            ("SPL", "Samples", "Sample the animation at a given rate", 1),
        ],
        default="KFR",
    )

    multiplier : IntProperty(
        name="Sample Frame Multiplier",
        description="Sample Frame Multiplier - Determines number of precomputed samples using (number of keyframes) * (sample frame multiplier)",
        default=4,
        soft_min=4,
        soft_max=20,
    )

    subdivisions : IntProperty(
        name="Subdivisions",
        description="Number of times to subdivide an animation when exporting samples. This subdivision is made for each animation individually.",
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

    def execute(self, context):
        keywords = self.as_keywords(ignore=("check_existing", "filter_glob", "ui_tab"))
        return export_smf(self, context, **keywords)

    def draw(self, context):
        # Everything gets displayed through the panels that are defined below
        pass

class SMF_PT_export_general(bpy.types.Panel):
    bl_space_type = 'FILE_BROWSER'
    bl_region_type = 'TOOL_PROPS'
    bl_label = "General"
    bl_parent_id = "FILE_PT_operator"

    @classmethod
    def poll(cls, context):
        sfile = context.space_data
        operator = sfile.active_operator

        return operator.bl_idname == "EXPORT_SCENE_OT_smf"

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False  # No animation.

        sfile = context.space_data
        operator = sfile.active_operator

        layout.prop(operator, 'export_textures')

class SMF_PT_export_advanced(bpy.types.Panel):
    bl_space_type = 'FILE_BROWSER'
    bl_region_type = 'TOOL_PROPS'
    bl_label = "Advanced"
    bl_parent_id = "FILE_PT_operator"

    @classmethod
    def poll(cls, context):
        sfile = context.space_data
        operator = sfile.active_operator

        return operator.bl_idname == "EXPORT_SCENE_OT_smf"

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False  # No animation.

        sfile = context.space_data
        operator = sfile.active_operator

        layout.label(text="General")
        layout.prop(operator, 'anim_export_mode')
        layout.prop(operator, 'anim_length_mode')

        layout.label(text="Specifics")
        layout.prop(operator, 'export_type')
        layout.prop(operator, 'multiplier')
        if operator.export_type == 'SPL':
            layout.prop(operator, 'subdivisions')

        layout.label(text="Other")
        layout.prop(operator, 'interpolation')
        #layout.prop(operator, "scale")

def menu_func_export(self, context):
    self.layout.operator(ExportSMF.bl_idname, text="SMF (*.smf)")


def menu_func_import(self, context):
    self.layout.operator(ImportSMF.bl_idname, text="SMF (*.smf)")


classes = (
    SMF_PT_export_general,
    SMF_PT_export_advanced,
    ExportSMF,
    ImportSMF,  # Uncomment this to enable the WIP importer
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
