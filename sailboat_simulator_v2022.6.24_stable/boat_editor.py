#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  boat_editor.py
#  
#  Copyright 2022 Hadrian Ward <hadrian.f.ward@gmail.com>
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
import os, json, sys

# third-party, from PyPi
import tkinter as tk
from pymunk.vec2d import Vec2d# very useful
from PIL import Image as image
from PIL import ImageTk as image_tk

# from CWD
import extras, graphics, simulator, GUIs

# classes
class BoatEditor:
	'''
	GUI for editing a boat
	'''
	def __init__(s, frame:tk.Frame, boat_name:str, close_callback=None):
		'''
		init GUI and load boat
		:param frame: Tk frame
		:param boat_name: name of boat file
		:param close_callback: function to call when closed
		'''
		# save params
		s.frame = frame
		s.boat_name = boat_name
		s.close_callback = close_callback
		# defaults
		s.wind = Vec2d(0, 0)
		s.movement_locks = {
			'translation': tk.BooleanVar(),
			'rotation': tk.BooleanVar()
		}
		# load settings
		s.GUI_settings = extras.load_settings(type_='GUI')
		s.sim_settings = extras.load_settings(type_='simulator')
		# create objects
		s.pixel_units = graphics.CommonPixelUnits(s.GUI_settings['pixel-units'])
		# load boat
		os.chdir(extras.resources.boat_dir)
		with open(boat_name + '.json') as f:
			s.boat_static_config = json.loads(f.read())
		s.boat_dynamic_config = simulator.SuperSailboat.get_new_dict(boat_name=boat_name)
		s.boat_graphic_renderer = graphics.SailboatRenderer(
			static_config=s.boat_static_config,
			config=s.boat_dynamic_config,
			settings=s.GUI_settings,
			time_logger=extras.TimeLogger(),
			pixel_units=s.pixel_units,
			font=graphics.mono_font,
			username=s.boat_name
		)
		s.boat_physics_renderer = simulator.Sailboat(
			time_logger=extras.TimeLogger(),
			config=s.boat_dynamic_config,
			settings=s.sim_settings
		)
		# setup GUI
		img_col, control_panel_col = {'l': [1, 0], 'r': [0, 1]}[s.GUI_settings['control-panel-side'].lower()]
		# image label
		s.curr_tk_img = image_tk.PhotoImage(image.new('RGB', (10, 10), (255, 255, 255)))
		s.img_label = tk.Label(s.frame, image=s.curr_tk_img)
		s.img_label.grid(row=0, column=img_col, sticky='nsew')
		s.frame.grid_rowconfigure(0, weight=1)
		s.frame.grid_columnconfigure(img_col, weight=1)
		# control panel frame
		s.controls_frame = tk.Frame(s.frame)
		s.controls_frame.grid(row=0, column=control_panel_col)
		# --------------controls--------------
		curr_row = 0
		# lock movement checkbuttons
		for name, tk_var in s.movement_locks.items():
			curr_row += 1
			tk.Checkbutton(s.controls_frame, text=f'Lock {name}', variable=tk_var).grid(row=curr_row, column=0)
		# close button
		curr_row += 1
		tk.Button(s.controls_frame, text='Close', command=s.close).grid(row=curr_row, column=0)
		# ------------------------------------
		# "resize" to set image size correctly
		s.resized((s.frame.winfo_width(), s.frame.winfo_height()))
		# render image
		s.render_img()
		# record time
		s.prev_t_micros = extras.micros()

	def update(s) -> None:
		'''
		updates the boat simulation
		:return: None
		'''
		# timing
		frame_t = (extras.micros() - s.prev_t_micros) / 1_000_000
		s.prev_t_micros = extras.micros()

	def update_boat(s) -> None:
		'''
		updates the boat renderer
		:return: None
		'''
		s.boat_graphic_renderer.setup_static_specs(s.boat_static_config)
		s.boat_graphic_renderer.update(config=s.boat_dynamic_config, global_wind=s.wind)
		s.render_img()

	def render_img(s) -> None:
		'''
		updates image
		:return: None
		'''
		# create image
		s.img = image.new('RGB', s.img_size, (128, 128, 128))
		# render boat
		s.boat_graphic_renderer.render_img(img=s.img, global_point_to_img_point=s.boat_graphic_renderer.global_point_to_img_point, main_vector_convertor=s.boat_graphic_renderer.convert_vector, main=True, enabled=True)
		# update image to GUI
		s.curr_tk_img = image_tk.PhotoImage(s.img)
		s.img_label.config(image=s.curr_tk_img)

	def resized(s, size:tuple) -> None:
		'''
		called when main frame is resized
		:param size: new size
		:return: None
		'''
		# recalculate image size
		s.img_size = (max(size[0] - s.controls_frame.winfo_width() - 4, 10), max(size[1] - 4, 10))
		# update image
		s.render_img()

	def close(s) -> None:
		'''
		makes sure that boat is saved
		:return: None
		'''
		if not (s.close_callback is None):
			s.close_callback()

	def save(s) -> None:
		'''
		saves boat static config
		:return: None
		'''
		os.chdir(extras.resources.boat_dir)
		with open(s.boat_name + '.json') as f:
			f.write(json.dumps(s.boat_static_config))


class MainGUI:
	'''
	main GUI
	'''
	def __init__(s, master:tk.Tk, close_callback=None):
		'''
		init GUI
		:param master: Tk window
		:param close_callback: function to call when closed
		'''
		# save params
		s.master = master
		s.close_callback = close_callback
		# setup GUI
		s.screen_size = (s.master.winfo_screenwidth(), s.master.winfo_screenheight())
		s.setup_gui()

	def setup_gui(s, mode:str='home') -> None:
		'''
		sets up te GUI
		:param mode: either "home" or "editor"
		:return: None
		'''
		assert mode in ['home', 'editor'], 'mose must be either "home" or "editor"'
		try:
			s.frame.destroy()
			del s.frame
		except AttributeError:
			pass
		s.frame = tk.Frame(s.master)
		resizable = {'home': False, 'editor': True}[mode]
		if resizable:
			s.frame.grid(row=0, column=0, sticky='nsew')
			s.master.resizable(True, True)
			s.master.grid_rowconfigure(0, weight=1)
			s.master.grid_columnconfigure(0, weight=1)
			s.master.geometry(f'{str(s.screen_size[0] - 100)}x{str(s.screen_size[1] - 100)}+50+50')
		else:
			s.master.minsize(0, 0)
			s.master.attributes('-fullscreen', False)
			s.master.resizable(False, False)
			s.frame.grid(row=0, column=0)
		curr_row = 0
		if mode == 'home':
			# row 0: label
			tk.Label(s.frame, text='Boat Editor\nLoad existing boat\n--------------------').grid(row=curr_row, column=0)
			# row 1: open existing boat frame
			curr_row += 1
			# create frame
			s.load_frame = tk.Frame(s.frame)
			s.load_frame.grid(row=curr_row, column=0)
			# boat select frame
			s.boat_select_frame = tk.Frame(s.load_frame)
			s.boat_select_frame.grid(row=0, column=0)
			# load button
			s.load_button = tk.Button(s.load_frame, text='Load', command=s.start_editor, state='disabled')
			s.load_button.grid(row=0, column=1)
			# boat select GUI
			s.boat_select_GUI = GUIs.ResourceList(
				frame=s.boat_select_frame,
				type_='boats',
				change_valid_callback=lambda _: s.load_button.config(state='normal')
			)
			# row 2: new frame
			curr_row += 1
			# create frame
			s.new_frame = tk.Frame(s.frame)
			s.new_frame.grid(row=curr_row, column=0)
			# label
			tk.Label(s.new_frame, text='Create a new boat\n--------------------').grid(row=0, column=0, columnspan=2)
			# entry
			s.new_boat_entry = tk.Entry(s.new_frame)
			s.new_boat_entry.grid(row=1, column=0)
			s.new_boat_entry.bind('<KeyRelease>', lambda _: s.new_button.config(state=['disabled', 'normal'][int(bool(s.new_boat_entry.get()))]))
			# button
			s.new_button = tk.Button(s.new_frame, text='Create new', command=s.new, state='disabled')
			s.new_button.grid(row=1, column=1)
			# row 3: close button
			curr_row += 1
			tk.Button(s.frame, text='Close', command=s.close).grid(row=curr_row, column=0)
		if mode == 'editor':
			s.frame.bind('<Configure>', lambda e: s.editor.resized((e.width, e.height)))

	def start_editor(s) -> None:
		'''
		called by button, starts boat editor
		:return: None
		'''
		# get boat name
		boat_name = s.boat_select_GUI.get()
		# setup GUI for the editor
		s.setup_gui(mode='editor')
		# create editor
		s.editor = BoatEditor(frame=s.frame, boat_name=boat_name, close_callback=s.setup_gui)

	def new(s) -> None:
		'''
		TODO: assert new boat name doesn't already exist
		called by button, creates new boat and starts editor
		:return: None
		'''
		# create new boat
		new_boat_name = extras.validate_filename(s.new_boat_entry.get())
		os.chdir(extras.resources.boat_dir)
		with open(new_boat_name + '.json', 'w') as f:
			f.write(json.dumps(simulator.SuperSailboat.static_config_template()))
		# recreate GUI so boat list is reloaded
		s.setup_gui()

	def close(s) -> None:
		'''
		makes sure that boat is saved
		:return: None
		'''
		# TODO: make sure boat is saved
		if not (s.close_callback is None):
			s.close_callback()


def main():
	root = tk.Tk()
	root.wm_title(f'Boat Editor - Sailboat Simulator v{extras.__version__}')
	main_gui = MainGUI(master=root, close_callback=root.quit)
	print('starting the tkinter GUI')
	try:
		root.mainloop()
	except KeyboardInterrupt:
		main_gui.close()
	print('END')
	return 0

if __name__ == '__main__':
	sys.exit(main())
