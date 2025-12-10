#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  map_editor.py
#  
#  Copyright 2022 Hadrian Ward
#  
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  (at your option) any later version.
#  
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#  
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA 02110-1301, USA.
#  
#  

# imports
# built-ins
import os, json, time, copy, traceback, random, webbrowser, math
import multiprocessing as mp
import datetime as dt

# third-party, from PyPi
import pint
import tkinter as tk
from pymunk.vec2d import Vec2d# very useful
from send2trash import send2trash
from PIL import Image as image
from PIL import ImageTk as image_tk

# from CWD
import GUIs, extras, graphics, simulator

# classes
class MapEditor:
    '''
    class for handling the GUI for editing a map
    '''
    def __init__(s, frame:tk.Frame, name:str):
        '''
        init with the name of a map file
        :param frame: tkinter frame
        :param name: map file name without extension
        '''
        # save params
        s.frame = frame
        s.name = name
        # init objects
        s.renderer = graphics.MapRenderer()# TODO
        # flags and defaults
        s.mouse_states = ['name', 'select', 'move', 'new', 'delete']
        s.mouse_state = 'select'

    def create_gui(s) -> None:
        '''
        creates the GUI
        :return:
        '''
        pass# TODO

if __name__ == '__main__':
    print('this program does not run by itself, run main.py and use the GUI')
