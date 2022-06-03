# SMF export scripts for Blender
#
#from .pydq import dq_create_matrix_vector, dq_to_tuple_smf
import bpy
from struct import Struct, calcsize
from mathutils import *
from math import *
from os import path

import time

# Used for much faster image loading
import numpy as np

SMF_version = 7
SMF_format_struct = Struct("ffffffffBBBBBBBBBBBB")  # 44 bytes
SMF_format_size = SMF_format_struct.size

### IMPORT ###

from struct import unpack, unpack_from

from .pydq import (
    dq_create_iterable,
)

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
    modName = path.basename(filepath)
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
    print(versionNum)

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

    print(texPos, matPos, modPos, nodPos, colPos, rigPos, aniPos, selPos, subPos)
    print(placeholder)
    print("Number of models:", modelNum)

    img = None

    n = unpack_from("B", data, offset=texPos)[0]
    print("Textures: ", n)

    # Read texture images
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

        if name in bpy.data.images:
            # Already an image with the given name
            img = bpy.data.images[name]
        else:
            # No image with this name exists, add a new one
            img = bpy.data.images.new(
                name=name,
                width=dimensions[0],
                height=dimensions[1],
            )
            print("Read Image Data")
            start = time.perf_counter_ns()

            # Unacceptably slow way
            """
            for i in range(0, dimensions[0]*dimensions[1]):
                rgba = data[offset+i*4:offset+i*4+4]
                rgba = [co/255 for co in rgba]
                img.pixels[i*4:i*4+4] = rgba[:]
            """

            # Much faster way to set image data using NumPy
            # TODO Adjust use of foreach_set based on Blender version used
            # (foreach_set/foreach_get are fairly recent additions)
            image_data = np.frombuffer(data, dtype = np.ubyte, count = 4*num_pixels, offset = offset)
            image_data = (image_data / 255).astype(np.float)
            img.pixels.foreach_set(tuple(image_data))

            end = time.perf_counter_ns()

            print(str((end-start)/1000) + "us")

        offset += 4 * num_pixels

    # Read model data
    # Create a new Blender 'MESH' type object for every SMF model
    print("Read model data...")
    dataPos = modPos
    for model_index in range(modelNum):
        size = unpack_from("I", data, offset=dataPos)[0]
        pos = dataPos + 4
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

        # TODO Use filename without ext here
        mesh = bpy.data.meshes.new(modName)
        bm.to_mesh(mesh)

        matName = unpack_string_from(data, offset=pos)
        pos = pos + len(matName) + 1
        texName = unpack_string_from(data, offset=pos)
        pos = pos + len(texName) + 1
        print(matName, texName)

        visible = unpack_from("B", data, offset=pos)[0]
        pos += 1
        skinning_info = unpack_from("II", data, offset=pos)[0]
        # if != (0, 0) ??
        pos += 2*4


        bpy.ops.object.add(type="MESH")
        new_obj = bpy.context.active_object
        new_obj.name = mesh.name    # Let Blender handle the number suffix
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

        # Advance to next model
        dataPos = pos

    # Read rig info and construct armature
    node_num = unpack_from("B", data, offset = rigPos)[0]
    if node_num > 0:
        bpy.ops.object.armature_add(enter_editmode=True)
        print("Meeeh")
        armature_object = bpy.data.objects[-1:][0]
        armature = armature_object.data
        bpy.ops.armature.select_all(action='SELECT')
        bpy.ops.armature.delete()   # Delete default bone

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

            """
            rot_quat = Quaternion((dq[3], dq[0], dq[1], dq[2]))
            tr_quat = Quaternion((dq[7], dq[4], dq[5], dq[6]))
            dq_nt = dq_create_iterable(dq, w_last = True)  # SMF puts w last
            new_tail = Vector((2 * (tr_quat @ rot_quat.conjugated()))[1:4])
            if bone_list and parent_bone_index >= 0:
                new_bone.parent = bone_list[parent_bone_index]
                new_bone.use_connect = is_bone
            new_bone.tail = new_tail
            print(new_bone.matrix, new_bone.tail[:])
            """

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

    bpy.ops.object.editmode_toggle()

    return {'FINISHED'}
