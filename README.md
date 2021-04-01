# Blender to SMF
Attempt at export of Blender model to SMF model format

## Format


## Plugin support


## Other

### Adding a texture for export to SMF
The add-on looks for a directly connected Image Texture node on the Base Color input of the shader that is connected to the Material Output node.

To setup a valid material for this work you have to perform the following steps: 

* Add a new material to the mesh object. The material uses nodes by default.
* Under `Surface`, click on the yellow circle behind `Base Color` and under `Texture` select `Image Texture`.
* Click the `Open` button to select the image file that you want to use as the texture image for this material.
* To verify the node tree you can open the `Shading` tab. Note how all the nodes are properly connected.