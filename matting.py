#!/usr/bin/env python3
#   Copyright (C) 1997  James Henstridge <james@daa.com.au>
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation; either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with this program.  If not, see <https://www.gnu.org/licenses/>.

import gi
gi.require_version('Gimp', '3.0')
from gi.repository import Gimp
gi.require_version('GimpUi', '3.0')
from gi.repository import GimpUi
from gi.repository import GObject
from gi.repository import GLib
from gi.repository import Gio
from gi.repository import Gegl
import os
import tempfile
# Gegl.init()

import sys

def N_(message): return message
def _(message): return GLib.dgettext(None, message)

from pymatting.util.util import load_image, save_image, stack_images
from pymatting.alpha.estimate_alpha_cf import estimate_alpha_cf
from pymatting.foreground.estimate_foreground_ml import estimate_foreground_ml
import numpy

def decompose(image, trimap):
    if image.shape[:2] != trimap.shape[:2]:
        raise ValueError("Input image and trimap must have same size")

    alpha = estimate_alpha_cf(image, trimap)
    foreground, background = estimate_foreground_ml(image, alpha, return_background=True)

    fore = stack_images(foreground, alpha)
    back = stack_images(background, 1 - alpha)

    return fore, back

def layer_to_numpy(image, drawable, mode):
    if mode is None:
        if drawable.is_rgb():
            mode = "RGB"
        elif drawable.is_gray():
            mode = "GRAY"
        else:
            raise Exception("ERROR")
    filepath = os.path.join(tempfile.gettempdir(), "image.png")
    file = Gio.file_new_for_path(filepath)
    Gimp.file_save(Gimp.RunMode.NONINTERACTIVE, image, [drawable], file)
    return load_image(filepath, mode)
    
def numpy_to_layer(image, nparray):
    filepath = os.path.join(tempfile.gettempdir(), "image.png")
    file = Gio.file_new_for_path(filepath)
    save_image(filepath, nparray)
    result_layer = Gimp.file_load_layer(Gimp.RunMode.NONINTERACTIVE, image, file)
    mask = result_layer.create_mask(3)
    result_layer.add_mask(mask)
    #drawables[0].add_mask(mask)
    return result_layer

# Returns NP array (N,bpp) (single vector ot triplets)
def channelData(layer):
    region=layer.get_pixel_rgn(0, 0, layer.width,layer.height)
    pixChars=region[:,:] # Take whole layer
    bpp=region.bpp
    return np.frombuffer(pixChars,dtype=np.uint8).reshape(len(pixChars)/bpp,bpp)

def drawableData(drawable):
    width = drawable.get_width()
    height = drawable.get_height()
    
    buffer = drawable.get_buffer()
    
    rect = Gegl.Rectangle.new(0, 0, width, height)
    src_pixels = buffer.get(rect, 1.0, None, Gegl.AbyssPolicy.CLAMP)
    
    #GObject.Object.unref(buffer)
    return src_pixels

def createResultLayer(image,name,result):
    rlBytes=np.uint8(result).tobytes();
    rl=gimp.Layer(image,name,image.width,image.height,image.active_layer.type,100,NORMAL_MODE)
    region=rl.get_pixel_rgn(0, 0, rl.width,rl.height,True)
    region[:,:]=rlBytes
    image.add_layer(rl,0)
    gimp.displays_flush()

def cutout(procedure, run_mode, image, n_drawables, drawables, args, data):
    #config = procedure.create_config()
    #config.begin_run(image, run_mode, args)
    
    if run_mode == Gimp.RunMode.INTERACTIVE:
        GimpUi.init('pymatting')
    
    Gimp.context_push()
    image.undo_group_start()
    # if image.get_base_type() is Gimp.ImageBaseType.RGB:
    #     type = Gimp.ImageType.RGBA_IMAGE
    # else:
    #     type = Gimp.ImageType.GRAYA_IMAGE
    
    if "trimap" in drawables[0].get_name():
        raise Error("0 is trimap")
    if "trimap" not in drawables[1].get_name():
        raise Error("1 is not trimap")
    print("starting")

    combined = layer_to_numpy(image, drawables[0], "RGB")
    trimap = layer_to_numpy(image, drawables[1], "GRAY")
    
    F,B = decompose(combined, trimap)
    F = numpy_to_layer(image, F)
    F.set_name("foreground")
    B = numpy_to_layer(image, B)
    B.set_name("background")
    
    image.insert_layer(F, drawables[0].get_parent(), image.get_item_position(drawables[0]))
    image.insert_layer(B, drawables[0].get_parent(), image.get_item_position(drawables[0]))


    Gimp.displays_flush()

    image.undo_group_end()
    Gimp.context_pop()

    #config.end_run(Gimp.PDBStatusType.SUCCESS)

    return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, GLib.Error())

class Matting (Gimp.PlugIn):
    ## GimpPlugIn virtual methods ##
    def do_set_i18n(self, procname):
        return True, 'gimp30-python', None

    def do_query_procedures(self):
        return [ 'pymatting' ]

    def do_create_procedure(self, name):
        procedure = Gimp.ImageProcedure.new(self, name,
                                            Gimp.PDBProcType.PLUGIN,
                                            cutout, None)
        procedure.set_image_types("RGB*, GRAY*");
        procedure.set_sensitivity_mask (Gimp.ProcedureSensitivityMask.DRAWABLE |
                                        Gimp.ProcedureSensitivityMask.DRAWABLES)
        procedure.set_documentation (_("Alpha Matting"),
                                     _("Decompose a layer by alpha matting."),
                                     name)
        procedure.set_menu_label(_("_Matting..."))
        procedure.set_attribution("Songun Lee",
                                  "Songun Lee",
                                  "2022,2022")
        procedure.add_menu_path ("<Image>/Filters/Map")
        return procedure

Gimp.main(Matting.__gtype__, sys.argv)
