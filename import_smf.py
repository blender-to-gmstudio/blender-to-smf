# SMF import scripts for Blender
#
#
#
#

import time
from math import *
from mathutils import *
from pathlib import Path
from struct import (
    Struct,
    calcsize,
    unpack,
    unpack_from,
)

# Used for much faster image loading
import numpy as np

# Make sure to reload changes to code that we maintain ourselves
# when reloading scripts in Blender
if "bpy" in locals():
    import importlib
    if "pydq" in locals():
        importlib.reload(pydq)

import bpy

from . import pydq
from .pydq import dq_create_iterable

# SMF definitions
SMF_version = 7
SMF_format_struct = Struct("ffffffffBBBBBBBBBBBB")  # 44 bytes
SMF_format_size = SMF_format_struct.size

def unpack_string_from(data, offset=0):
    """Unpacks a zero terminated string from the given offset in the data"""
    result = ""
    while data[offset] != 0:
        result += chr(data[offset])
        offset += 1
    return result

def import_smf_file(operator, context,
               filepath,
               create_new_materials_images,
               ):
    """
    Main entry point for SMF import
    """

    import bmesh
    modName = Path(filepath).stem
    print("Model file: " + str(modName))

    data = bytearray()
    with open(filepath, 'rb') as file:
        data = file.read()

    header_bytes = unpack_from("17s", data)[0]
    header_text = "".join([chr(b) for b in header_bytes])
    #print(header_text)

    # SMF file?
    if header_text != "SnidrsModelFormat":
        print("File does not contain a valid SMF file. Exiting...")
        return {'FINISHED'}

    # Valid SMF v7 file?
    versionNum = int(unpack_from("f", data, offset=18)[0])
    print("SMF version:", versionNum)

    if versionNum != 7:
        print("Invalid SMF version. The importer currently only supports SMF v7.")
        return {'FINISHED'}

    texPos, matPos, modPos, nodPos, colPos, rigPos, aniPos, selPos, subPos, placeholder = unpack_from(
        "I"*10,
        data,
        offset=18+4,
    )

    # Read number of models
    modelNum = unpack_from("B", data, offset = 62)[0]

    print("Number of models:", modelNum)

    img = None

    n = unpack_from("B", data, offset=texPos)[0]
    print("Textures: ", n)

    # Read texture images
    #
    # In current SMF, textures and materials are the same
    # So for every texture we need to add a material as well
    material_map = {}
    offset = texPos+1
    for i in range(n):
        name = unpack_string_from(data, offset)
        offset = offset + len(name) + 1
        dimensions = (
            unpack_from("H", data, offset=offset)[0],
            unpack_from("H", data, offset=offset+2)[0],
        )
        offset = offset+4
        print("Name: ", name)
        print("Dimensions: ", dimensions)

        num_pixels = dimensions[0] * dimensions[1]
        print("Num pixels: ", num_pixels)

        if create_new_materials_images:
            # Create new material and image no matter what the .blend file contains
            img = image_from_data(name, dimensions, data, offset)
            mat = material_with_texture(name, img)
        else:
            if name in bpy.data.materials:
                # A material with the image name already exists => use it!
                #
                # Note how this may link to a material that has a wrong texture
                # assigned to it or even no texture at all (!)
                mat = bpy.data.materials[name]
            else:
                # Create new material and image (since it doesn't exist yet)
                img = image_from_data(name, dimensions, data, offset)
                mat = material_with_texture(name, img)

        offset += 4 * num_pixels

        material_map[img.name] = mat

    # Read model data
    # Create a new Blender 'MESH' type object for every SMF model
    print("Read model data...")
    print("Meshes:", modelNum)
    dataPos = modPos
    for model_index in range(modelNum):
        size = unpack_from("I", data, offset=dataPos)[0]
        pos = dataPos + 4
        print(modName, model_index)
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

        # Add mesh
        mesh = bpy.data.meshes.new(modName)
        bm.to_mesh(mesh)

        # Read mesh's material and texture image name
        # The texture image acts as the key!
        matName = unpack_string_from(data, offset=pos)
        pos = pos + len(matName) + 1
        texName = unpack_string_from(data, offset=pos)  # Image name
        pos = pos + len(texName) + 1
        print("Material:", matName)
        print("Image:", texName)

        visible = unpack_from("B", data, offset=pos)[0]
        pos += 1
        skinning_info = unpack_from("II", data, offset=pos)[0]
        # if != (0, 0) ??
        pos += 2*4

        bpy.ops.object.add(type="MESH")
        new_obj = bpy.context.active_object
        new_obj.name = mesh.name    # Let Blender handle the number suffix
        new_obj.data = mesh

        # Add a material slot and assign the material to it
        bpy.ops.object.material_slot_add()

        mat_final = None
        if create_new_materials_images:
            if texName in bpy.data.materials:
                mat_final = bpy.data.materials[texName]
            else:
                # Empty material slot... => unwanted
                pass
        else:
            mat_final = bpy.data.materials[texName]

        new_obj.material_slots[0].material = mat_final

        # Advance to next model
        dataPos = pos

    # Read rig info and construct armature
    node_num = unpack_from("B", data, offset = rigPos)[0]
    if node_num > 0:

        # Create armature
        bpy.ops.object.armature_add(enter_editmode=True)
        armature_object = bpy.data.objects[-1:][0]
        armature = armature_object.data
        bpy.ops.armature.select_all(action='SELECT')
        bpy.ops.armature.delete()   # Delete default bone

        # Add the bones
        bone_list = []
        item_bytesize = calcsize("ffffffffBB")
        print("Number of nodes", node_num)
        for node_index in range(node_num):
            data_tuple = unpack_from("ffffffffBB", data,
                        offset = rigPos+1 + node_index*item_bytesize)
            dq = dq_create_iterable(data_tuple[0:8], w_last = True) # SMF stores w last
            parent_bone_index = data_tuple[8]
            is_bone = data_tuple[9]
            bpy.ops.armature.bone_primitive_add()
            new_bone = bpy.context.object.data.edit_bones[-1:][0]
            bone_list.append(new_bone)

            # Old attempt
            # """
            new_tail = Vector((2 * (dq.dual @ dq.real.conjugated()))[1:4])
            if bone_list and parent_bone_index >= 0:
                new_bone.parent = bone_list[parent_bone_index]
                new_bone.use_connect = is_bone
            new_bone.tail = new_tail
            # print(new_bone.matrix, new_bone.tail[:])
            # """

            # New attempt: do the exporter's conversion backwards
            # TODO!


        bpy.ops.armature.select_all(action='DESELECT')
        for bone in bpy.context.object.data.edit_bones:
            if not bone.use_connect:
                bone.select = True
        bpy.ops.armature.delete()   # What about the root node/bone?

    # Read animations and add actions to the armature
    # todo
    """
    anim_num = unpack_from("B", data, offset = aniPos)
    print(anim_num)
    for anim_index in range(anim_num):
            anim_name = unpack_string_from(data, offset=aniPos+1)
            print(anim_name)
            #anim = bpy.data.actions.new(anim_name)"""

    bpy.ops.object.mode_set(mode='OBJECT')

    return {'FINISHED'}


def image_from_data(name, dimensions, data, offset):
    """Create a new image (bpy.types.Image) from the data"""

    img = bpy.data.images.new(
        name=name,
        width=dimensions[0],
        height=dimensions[1],
    )

    # Read the image data
    print("Read Image Data")

    start = time.perf_counter_ns()

    # Process image data using NumPy, then use Image.pixels.foreach_set
    num_pixels = dimensions[0] * dimensions[1]
    image_data = np.frombuffer(data, dtype = np.ubyte, count = 4*num_pixels, offset = offset)
    image_data = (image_data / 255).astype(np.float)
    img.pixels.foreach_set(tuple(image_data))

    end = time.perf_counter_ns()

    print(str((end-start)/1000) + "us")

    return img

def material_with_texture(name, image):
    """Create a new material using nodes with the image as the base color input"""

    mat = bpy.data.materials.new(name)
    mat.use_nodes = True

    mat.node_tree.nodes.new(type="ShaderNodeTexImage")  # This is the bl_rna identifier, NOT the type!
    image_node = mat.node_tree.nodes['Image Texture']   # Default name
    image_node.image = image
    shader_node = mat.node_tree.nodes["Principled BSDF"]
    mat.node_tree.links.new(image_node.outputs['Color'], shader_node.inputs['Base Color'])

    return mat
