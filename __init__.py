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
from .smf import export_smf, import_smf

# ExportHelper is a helper class, defines filename and
# invoke() function which calls the file selector.
from bpy_extras.io_utils import ExportHelper, ImportHelper

from bpy.props import StringProperty, BoolProperty, EnumProperty, IntProperty
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
    bl_options = {'REGISTER'}

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
    
    # "Advanced" export settings
    export_nla_tracks : BoolProperty(
            name="Export NLA Tracks",
            description="Whether to export multiple animations on all NLA tracks that are linked to this model (Experimental)",
            default=False,
    )
    
    # TODO The below ones are to be added later
    #export_nla_tracks : EnumProperty(
    #    name="Animations",
    #    description="How to export animations",
    #    items=[
    #        ("CUR","Current Action", "Export the Armature's current action", 0),
    #        ("LNK","Linked NLA Actions", "Export all actions that are linked indirectly through NLA tracks", 1),
    #        ("TRA","NLA Tracks", "Export each NLA track as a separate animation", 2),
    #        ("SCN","Scene", "Export directly from the scene. This allows for the most advanced animations", 3),
    #    ],
    #    default="CUR",
    #)
    
    export_type : EnumProperty(
        name="Export Type",
        description="What to export",
        items=[
            ("KFR", "Keyframes", "Export all keyframes", 0),
            ("SPL", "Samples", "Sample the animation at a given rate", 1),
        ],
        default="KFR",
    )
    
    mult : IntProperty(
        name="Multiplier",
        description="Sample Frame Multiplier - Determines number of precomputed samples using (number of keyframes) * (sample frame multiplier)",
        default=4,
        soft_min=4,
        soft_max=20,
    )

    def execute(self, context):
        # TODO Pass export parameters the proper way
        return export_smf(self.filepath, context, self.export_textures, self.export_nla_tracks, self.mult)


def menu_func_export(self, context):
    self.layout.operator(ExportSMF.bl_idname, text="SMF (*.smf)")


def menu_func_import(self, context):
    self.layout.operator(ImportSMF.bl_idname, text="SMF (*.smf)")


def register():
    bpy.utils.register_class(ExportSMF)
    bpy.utils.register_class(ImportSMF)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)


def unregister():
    bpy.utils.unregister_class(ExportSMF)
    bpy.utils.unregister_class(ImportSMF)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)


if __name__ == "__main__":
    register()
