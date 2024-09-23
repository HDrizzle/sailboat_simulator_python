#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  GUIs.py
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
import os, copy

# third-party, from PyPi
import tkinter as tk
from pymunk.vec2d import Vec2d
from PIL import Image as image
from PIL import ImageTk as image_tk

# from CWD
import extras

# classes
import graphics
import simulator


class GUISuperClass:
	'''
	superclass for all GUI classes
	'''
	def __init__(s, change_valid_callback=None, quit_callback=None):
		'''
		init
		:param change_valid_callback: callback function called when the user input validity changes:
			:param 1st: boolean representing if the current user input is valid
			:returns: ignored
		:param quit_callback: callback function to delete this GUI element
		'''
		# save params
		s.change_valid_callback = change_valid_callback
		s.quit_callback = quit_callback
		# flags
		s.valid = False# when the user has filled out all the entries correctly

	def set_valid(s, valid:bool) -> None:
		'''
		sets the valid state
		:param valid: whether the user has correctly filled out all the entries
		:return: None
		'''
		if valid != s.valid:
			s.valid = valid
			if s.change_valid_callback is not None:
				s.change_valid_callback(valid)

	def quit(s) -> None:
		'''
		calls the quit callback
		:return: None
		'''
		if s.quit_callback is not None:
			s.quit_callback()


class Form(GUISuperClass):
	'''
	superclass for a form
	'''
	def __init__(s, frame:tk.Frame, user_input_requirements:list, change_valid_callback=None):
		'''
		sets up the GUI
		:param frame: tkinter frame to use
		:param user_input_requirements: list of dicts of the following format:
			name: input name
			desc: input description, this is put on the label
			validator: function to validate input
				:param 1: (string) string from entry
				:returns: (bool) whether this entry is currently valid
			default: (optional) default value
		:param change_valid_callback: same as superclass
		'''
		# save params
		s.frame = frame
		s.user_input_requirements = user_input_requirements
		# init superclass
		super().__init__(change_valid_callback)
		# create widgets
		s.user_inputs = []
		curr_row = 0
		for d in user_input_requirements:
			d = {'default': '', **d}
			# label
			tk.Label(s.frame, text=d['desc']).grid(row=curr_row, column=0)
			# entry
			d['widget'] = tk.Entry(s.frame)
			d['widget'].grid(row=curr_row, column=1)
			d['widget'].insert(0, d['default'])
			d['widget'].bind('<KeyRelease>', lambda _: s.validate_inputs())
			curr_row += 1
			s.user_inputs.append(d)
		# validate inputs in case all the defaults make it valid
		s.validate_inputs()

	def validate_inputs(s) -> None:
		'''
		checks all the inputs
		:return: None
		'''
		valid = True
		for d in s.user_inputs:
			if not d['validator'](d['widget'].get()):
				valid = False
				d['widget'].config(fg='red')
			else:
				d['widget'].config(fg='black')
		s.set_valid(valid)

	def get_data(s) -> dict:
		'''
		gets the user input
		:return: dict:
			<input name>: input value
		'''
		return {d['name']: d['widget'].get() for d in s.user_inputs}


class AskJoinSimulation(Form):
	'''
	prompts the user to join a simulation
	'''
	def __init__(s, frame:tk.Frame, join_callback, quit_callback):
		'''
		sets up the GUI
		:param frame: tkinter frame to use
		:param join_callback: callback to join simulation
		:param quit_callback: callback function to call for the "cancel" button
		'''
		# save params
		s.frame = frame
		# setup frame
		curr_row = 0
		# row 0: label
		tk.Label(s.frame, text='Join a simulation').grid(row=curr_row, column=0)
		# row 1: inputs frame
		curr_row += 1
		s.inputs_frame = tk.Frame(s.frame)
		s.inputs_frame.grid(row=curr_row, column=0)
		# row 2: buttons frame
		curr_row += 1
		s.buttons_frame = tk.Frame(s.frame)
		s.buttons_frame.grid(row=curr_row, column=0)
		# join button
		s.join_button = tk.Button(s.buttons_frame, text='Join sim server', command=join_callback, state='disabled')
		s.join_button.grid(row=0, column=0)
		# cancel button
		tk.Button(s.buttons_frame, text='Cancel', command=quit_callback).grid(row=0, column=1)
		# init superclass
		user_inputs = [
			{'name': 'ip', 'desc': 'Server IPv4 address', 'validator': extras.validate_ipv4},
			{'name': 'port', 'desc': 'Server port', 'validator': extras.validate_port, 'default': str(extras.DEFAULT_PORT)},
			{'name': 'username', 'desc': 'Username', 'validator': lambda input_s: len(input_s) != 0},
			{'name': 'password', 'desc': 'Password', 'validator': lambda input_s: len(input_s) != 0},
			{'name': 'sim-password', 'desc': 'Sim server password', 'validator': lambda _: True}
		]
		super().__init__(frame=s.inputs_frame, user_input_requirements=user_inputs, change_valid_callback=lambda valid: s.join_button.config(state=['disabled', 'normal'][int(valid)]))


class NewSim(GUISuperClass):
	'''
	prompts the user to create a new simulation
	'''
	def __init__(s, frame:tk.Frame, wind_input_types, change_valid_callback):
		'''
		init
		:param frame: tk frame to use
		:param wind_input_types: dict ex.:
			<input-name>: [<min>, <max>, <res>]
		:param change_valid_callback: same as superclass
		'''
		# save params
		s.frame = frame
		s.wind_input_types = wind_input_types
		# init superclass
		super().__init__(change_valid_callback)
		# setup GUI
		# col 0: selections and name
		s.selections_frame = tk.Frame(s.frame)
		s.selections_frame.grid(row=0, column=0)
		# row 0: boat select
		curr_row = 0
		tk.Label(s.selections_frame, text='Select a boat').grid(row=curr_row, column=0)
		s.boat_select_frame = tk.Frame(s.selections_frame)
		s.boat_select_frame.grid(row=curr_row, column=1)
		s.boat_select_GUI = ResourceList(s.boat_select_frame, 'boats', lambda _: s.check_entries_valid())
		# row 1: map select
		curr_row += 1
		tk.Label(s.selections_frame, text='Select a map').grid(row=curr_row, column=0)
		s.map_select_frame = tk.Frame(s.selections_frame)
		s.map_select_frame.grid(row=curr_row, column=1)
		s.map_select_GUI = ResourceList(s.map_select_frame, 'maps', lambda _: s.check_entries_valid())
		# row 2: sim name
		# TODO: add validate callback that checks if sim already exists
		curr_row += 1
		tk.Label(s.selections_frame, text='Simulation name').grid(row=curr_row, column=0)
		s.new_sim_entry = tk.Entry(s.selections_frame, validatecommand=lambda name: extras.validate_filename(name) != None)
		s.new_sim_entry.grid(row=curr_row, column=1)
		s.new_sim_entry.bind('<KeyRelease>', lambda _: s.check_entries_valid())
		# row 3: password entry
		curr_row += 1
		tk.Label(s.selections_frame, text='Simulation password (optional)').grid(row=curr_row, column=0)
		s.password_entry = tk.Entry(s.selections_frame)
		s.password_entry.grid(row=curr_row, column=1)
		# col 1: wind settings
		s.wind_settings_frame = tk.Frame(s.frame)
		s.wind_settings_frame.grid(row=0, column=1)
		s.wind_input_GUI = simulator.WindGenerator.GUI(frame=s.wind_settings_frame)

	def check_entries_valid(s) -> None:
		'''
		checks if all the input widgets setup in the new sim window are filled out
		:return: None
		'''
		s.set_valid(s.boat_select_GUI.valid and s.map_select_GUI.valid and len(extras.validate_filename(s.new_sim_entry.get())) != 0)

	def get(s):
		'''
		gets all of the user input
		:return: dict:
			name: new sim name
			boat: boat name
			map: map name
			password: simulation password
			wind:
				<input-name>: value
		'''
		if s.valid:
			return {
				'name': extras.validate_filename(s.new_sim_entry.get()),
				'boat': s.boat_select_GUI.get(),
				'map': s.map_select_GUI.get(),
				'password': s.password_entry.get(),
				'wind': s.wind_input_GUI.get()
			}
		else:
			return None


class ResourceList(GUISuperClass):
	'''
	creates a listbox to list all of the available resource files of a certain type
	'''
	def __init__(s, frame:tk.Frame, type_:str, change_valid_callback=None):
		'''
		sets up the GUI
		:param frame: tk frame to use
		:param type_: type of resource to list, can be 'boats', 'maps', or 'sims'
		:param change_valid_callback: same as superclass
		'''
		# save param
		s.frame = frame
		s.type_ = type_
		# assertion
		assert type_ in ['boats', 'maps', 'sims']
		# init superclass
		super().__init__(change_valid_callback)
		# setup GUI
		curr_row = 0
		# row 0: listbox, last param from stackoverflow.com/questions/60336671
		s.resource_list = s.get_list(type_=type_)
		s.lst_box = tk.Listbox(s.frame, height=len(s.resource_list), selectmode=tk.BROWSE, exportselection=False)
		s.lst_box.bind('<1>', lambda _: s.set_valid(True))
		s.lst_box.grid(row=curr_row, column=0)
		for name in s.resource_list:
			s.lst_box.insert(tk.END, name)

	def get(s):
		'''
		gets the current name highlighted
		:return: current selected name or None
		'''
		assert s.valid, 'an item has to be selected'
		return s.resource_list[s.lst_box.curselection()[0]]

	@staticmethod
	def get_list(type_) -> list:
		'''
		gets list of given type
		:param type_: same as in __init__
		:return: list of names without extension
		'''
		# assertion
		assert type_ in ['boats', 'maps', 'sims']
		resource_dirs = {'boats': extras.resources.boat_dir, 'maps': extras.resources.maps_dir, 'sims': extras.resources.simulations_dir}
		os.chdir(resource_dirs[type_])
		return ['.'.join(name.split('.')[:-1]) for name in os.listdir(resource_dirs[type_]) if name.lower() != '.ds_store']


class AutopilotTargetInput(GUISuperClass):
	'''
	class for creating the GUI for the user to input a target position for the autopilot
	'''
	def __init__(s, frame:tk.Frame, change_valid_callback, users:list, end_pos:Vec2d):
		'''
		init (sets the input method to the default (pos)
		:param frame: tk frame to use
		:param change_valid_callback: same as superclass
		:param users: list of usernames that are on the server
		:param end_pos: end position to use for global pos default
		'''
		# save params
		s.frame = frame
		s.users = users
		s.end_pos = extras.convert_pos(end_pos, list)
		# init superclass
		super().__init__(change_valid_callback=change_valid_callback)

	def set_input_type(s, type_:str='pos') -> None:
		'''
		sets the state of the GUI for a specific input
		:param type_: pos input type
		:return: None
		'''
		assert type_ in ['pos', 'angle', 'user']
		s.type_ = type_
		s.valid = False
		# get rid of other widgets that may already exist
		[child.grid_forget() for child in s.frame.winfo_children()]
		if s.type_ == 'pos':
			default = list(map(str, s.end_pos))
			s.form = Form(
				s.frame,
				[
					{'name': 'x', 'desc': 'X: ', 'validator': lambda input_str: extras.validate_obj(input_str, float), 'default': default[0]},
					{'name': 'y', 'desc': 'Y: ', 'validator': lambda input_str: extras.validate_obj(input_str, float), 'default': default[1]}
				],
				s.set_valid
			)
		if s.type_ == 'angle':
			s.form = Form(
				s.frame,
				[
					{'name': 'length', 'desc': 'Course length: ', 'validator': lambda input_str: extras.validate_obj(input_str, float)},
					{'name': 'angle', 'desc': 'Angle (degrees): ', 'validator': lambda input_str: extras.validate_obj(input_str, float), 'default': '0'}
				],
				s.set_valid
			)
			s.set_valid(False)
		if s.type_ == 'user':
			curr_row = 0
			# row 0: user select listbox
			s.user_select = tk.Listbox(s.frame, height=len(s.users), selectmode=tk.BROWSE, exportselection=False)
			s.user_select.bind('<1>', lambda _: s.set_valid(True))
			s.user_select.grid(row=curr_row, column=0)
			for user in s.users:
				s.user_select.insert(tk.END, user)
			s.set_valid(False)# TODO: FIX: this doesn't work

	def get(s) -> list:
		'''
		gets the data to return to the server
		:return: see "resources" -> "simulation files" -> "clients" -> "autopilot" -> "target-pos" in documentation.html
		'''
		assert s.valid, 'the user input must be valid before it can be accessed'
		if s.type_ == 'pos':# global pos
			form_data = s.form.get_data()
			return ['global-pos', [float(form_data['x']), float(form_data['y'])]]
		if s.type_ == 'angle':# local pos
			form_data = s.form.get_data()
			vec = Vec2d(0, float(form_data['length'])).rotated_degrees(-float(form_data['angle']))
			return ['local-pos', list(vec)]
		if s.type_ == 'user':# track other boat
			return ['user', s.users[s.user_select.curselection()[0]]]


class AdminControlWindow:
	'''
	class for creating a popup window with controls for the admin
	'''
	def __init__(s,
			master_frame:tk.Frame,
			command_callback,
			global_reset_callback,
			usernames:list,
			boats_static_config:dict,
			settings:dict,
			user_boat_types:dict,
			map_data:dict):
		'''
		initiates flags
		:param master_frame: master frame to place frame on
		:param command_callback: reference to main.SimClient.admin_command()
		:param global_reset_callback: reference to main.SimClient.reset(global_=True)
		:param usernames: list of usernames on the server
		:param boats_static_config: dictionary:
			<boat type>: see "Resources" -> "Boat specs" in the docs
		:param settings: GUI settings
		:param user_boat_types: dictionary of each username and their boat type
		:param map_data: serialized map being used in the current simulation
		'''
		# save params
		s.master_frame = master_frame
		s.command_callback = command_callback
		s.global_reset_callback = global_reset_callback
		s.usernames = list(sorted(usernames))
		s.boats_static_config = boats_static_config
		s.load_settings(settings)
		s.user_boat_types = user_boat_types
		s.map_data = map_data
		# icon loader
		s.icons = IconContainer()
		# flags
		s.enabled = False
		s.user_selected = None
		s.sorted_usernames = []
		s.place_pos = [20, 20]
		s.global_wind = Vec2d(0, 0)

	def open_(s) -> None:
		'''
		sets up the GUI
		:return: None
		'''
		# check if closed
		if s.enabled:
			return
		# set flag
		s.enabled = True
		# create and place frame
		s.frame = tk.Frame(s.master_frame)
		s.frame.place(x=s.place_pos[0], y=s.place_pos[1])# TODO: place in the middle of the master frame
		# column 0: controls frame
		s.controls_frame = tk.Frame(s.frame)
		s.controls_frame.grid(row=0, column=0)
		# row 0: label
		curr_row = 0
		tmp = tk.Label(s.controls_frame, text='Administrator Controls (God Mode)', cursor='fleur')
		tmp.grid(row=curr_row, column=0)
		tmp.bind('<Button-1>', s.mouse_down)
		tmp.bind('<B1-Motion>', s.mouse_move)
		# row 1: user listbox
		curr_row += 1
		s.user_listbox = tk.Listbox(s.controls_frame, exportselection=False)
		s.user_listbox.grid(row=curr_row, column=0)
		s.user_listbox.bind('<<ListboxSelect>>', lambda _: s.user_selected_event(True))
		# row 2: user details
		curr_row += 1
		s.user_details_label = tk.Label(s.controls_frame, anchor=tk.W)
		s.user_details_label.grid(row=curr_row, column=0)
		# row 3: options for selected user
		curr_row += 1
		s.user_options_frame = tk.Frame(s.controls_frame)
		s.user_options_frame.grid(row=curr_row, column=0)
		# options
		tk.Button(s.user_options_frame, text='Reset', command=lambda: s.user_action('reset')).grid(row=0, column=0)
		tk.Button(s.user_options_frame, text='Toggle paused state', command=lambda: s.user_action('toggle-pause')).grid(row=0, column=1)
		tk.Button(s.user_options_frame, text='Block/Unblock', command=lambda: s.user_action('block-unblock')).grid(row=0, column=2)
		tk.Button(s.user_options_frame, text='Repair hull', command=lambda: s.user_action('repair')).grid(row=0, column=3)
		# row 4: general buttons button
		curr_row += 1
		s.general_buttons_frame = tk.Frame(s.controls_frame)
		s.general_buttons_frame.grid(row=curr_row, column=0)
		# close
		tk.Button(s.general_buttons_frame, text='Close', command=s.close).grid(row=0, column=0)
		# global reset
		tk.Button(s.general_buttons_frame, image=s.icons.get('refresh'), command=s.global_reset_callback).grid(row=0, column=1)
		# quit server
		tk.Button(s.general_buttons_frame, text='Quit server', command=lambda: s.command_callback(['QUIT'])).grid(row=0, column=2)
		# column 1: image
		s.img_size = (300, 300)
		s.curr_tk_img = image_tk.PhotoImage(image.new('RGB', s.img_size, (255, 255, 255)))
		s.img_label = tk.Label(s.frame, image=s.curr_tk_img)
		s.img_label.grid(row=0, column=1)
		# disable all user action buttons
		s.user_selected_event(False)
		# setup listbox
		s.setup_listbox(s.usernames)

	def load_settings(s, d:dict) -> None:
		'''
		loads settings
		:param d: GUI settings dict
		:return: None
		'''
		# save param
		s.settings = d
		# create pixel units
		s.pixel_units = graphics.CommonPixelUnits(s.settings['pixel-units'])

	def user_selected_event(s, state:bool) -> None:
		'''
		enables/disables all user option buttons
		:param state: whether a user is selected
		:return: None
		'''
		if state:
			# get selected user
			s.user_selected = s.usernames[s.user_listbox.curselection()[0]]
		else:
			s.user_selected = None
			s.curr_user_config = None
			s.users_admin_view_status = None
		try:
			del s.boat_renderer, s.map_renderer
		except Exception:
			pass
		s.user_details_label.config(text='')
		[widget.config(state=['disabled', 'normal'][int(state)]) for widget in s.user_options_frame.winfo_children()]

	def setup_state_data(s, curr_user_config:dict, users_admin_view_status:dict, global_wind:Vec2d) -> None:
		'''
		sets up the state data
		:param curr_user_config: see doc for simulator.Sailboat.serializable
		:param users_admin_view_status: dictionary:
			<username>: see simulator.ClientHandler.serializable('status-admin-view')
		:param global_wind: global wind vector
		:return: None
		'''
		# save params
		s.curr_user_config = curr_user_config
		s.users_admin_view_status = users_admin_view_status
		s.global_wind = global_wind
		if not (s.user_selected is None):
			# update label
			s.user_details_label.config(text=s.format_detail_string(s.user_selected))
			try:
				# update boat renderer
				s.boat_renderer.update(config=curr_user_config, global_wind=s.global_wind)
			except AttributeError:# first time
				# create renderer objects
				s.init_renderers()
				# scale pixel units
				s.pixel_units.scale(min(s.img_size) / (s.boat_renderer.perim_max_radius * s.pixel_units.get('distance') * 4))
			# update image
			s.img = image.new('RGB', s.img_size, (128, 128, 128))
			s.map_renderer.render_main(s.img)
			s.boat_renderer.render_img(img=s.img, global_point_to_img_point=s.boat_renderer.global_point_to_img_point, main_vector_convertor=s.boat_renderer.convert_vector, main=True, enabled=True)# TODO: get enabled state
			s.curr_tk_img = image_tk.PhotoImage(s.img)
			s.img_label.config(image=s.curr_tk_img)

	def init_renderers(s) -> None:
		'''
		initiates the map and boat renderers
		:return: None
		'''
		# boat
		s.boat_renderer = graphics.SailboatRenderer(
			static_config=s.boats_static_config[s.user_boat_types[s.user_selected]],
			config=s.curr_user_config,
			settings=s.settings,
			time_logger=extras.TimeLogger(),
			pixel_units=s.pixel_units,
			font=graphics.mono_font,
			username='no-username'
		)
		# map
		s.map_renderer = graphics.MapRenderer(
			config=copy.deepcopy(s.map_data),
			boat=s.boat_renderer,
			time_logger=extras.TimeLogger(),
			settings=s.settings,
			pixel_units=s.pixel_units
		)

	def setup_listbox(s, usernames:list) -> None:
		'''
		puts usernames in listbox
		:param usernames: list of usernames
		:return: None
		'''
		s.user_listbox.delete(0, tk.END)
		[s.user_listbox.insert(tk.END, name) for name in usernames]

	def format_detail_string(s, username:dict) -> str:
		'''
		formats a string about the user to display
		:param username: selected username
		:return: str
		'''
		user_dict = s.users_admin_view_status[username]
		return f'{["Unp", "P"][int(user_dict["paused"])]}aused{"   Blocked" * int(user_dict["blocked"])}   {["Off", "On"][int(user_dict["online"])]}line   IP: {user_dict["ip"]}   Password: {user_dict["password"]}'

	def user_action(s, action:str) -> None:
		'''
		does given action on selected user
		:param action: string
		:return: None
		'''
		assert s.user_selected is not None
		assert action in ['reset', 'toggle-pause', 'block-unblock', 'repair']
		if action == 'reset':
			s.command_callback(['USER-RESET', s.user_selected])
		if action == 'toggle-pause':
			s.command_callback(['USER-TOGGLE-PAUSE', s.user_selected])
		if action == 'block-unblock':
			s.command_callback([['USER-BLOCK', 'USER-UNBLOCK'][int(s.users_admin_view_status[s.user_selected]['blocked'])], s.user_selected])
		if action == 'repair':
			s.command_callback(['USER-REPAIR', s.user_selected])

	def mouse_move(s, e:tk.Event) -> None:
		'''
		called when the mouse is dragged on the title label
		:param e: tk event
		:return: None
		'''
		limits = (s.master_frame.winfo_width() - s.frame.winfo_width(), s.master_frame.winfo_height() - s.frame.winfo_height())
		new_pos = (e.x_root, e.y_root)
		delta = [new_pos - old_pos for new_pos, old_pos in zip(new_pos, s.root_mouse_pos)]
		s.place_pos = [max(0, min(old_place_pos + delta_c, limit)) for delta_c, limit, old_place_pos in zip(delta, limits, s.place_pos)]
		s.frame.place(x=s.place_pos[0], y=s.place_pos[1])
		s.root_mouse_pos = new_pos

	def mouse_down(s, e:tk.Event) -> None:
		'''
		callback for when the left mouse button is pressed
		:param e: event obj
		:return: None
		'''
		s.root_mouse_pos = (e.x_root, e.y_root)

	def close(s) -> None:
		'''
		closes the window
		:return: None
		'''
		# set flag
		s.enabled = False
		# unplace frame
		s.frame.place_forget()


class IconContainer:
	'''
	This loads all the images that start with "icon-" and stores them as ImageTk.PhotoImage objects
	'''
	def __init__(s):
		'''
		init
		'''
		# load icon images
		s.imgs = {}
		os.chdir(extras.imgs_dir)
		for name in os.listdir(extras.imgs_dir):
			if not name.startswith('icon-'):
				continue
			s.imgs[name[5:][:-4]] = image_tk.PhotoImage(image.open(name))

	def get(s, name:str) -> tk.PhotoImage:
		'''
		gets icon
		:param name: name of image
		:return: PhotoImage
		'''
		return s.imgs[name]
