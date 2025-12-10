#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  graphics.py
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
import math, os, copy
import datetime as dt

# third-party, from PyPi
import tkinter as tk
from pymunk.vec2d import Vec2d# very useful
from PIL import Image as image
from PIL import ImageTk as image_tk
from PIL import ImageFont as image_font
from PIL import ImageDraw as image_draw
from shapely.geometry import *

# from CWD
import extras, simulator

# classes
class CommonPixelUnits:
	'''
	class for syncing pixel unit data
	'''
	def __init__(s, pixel_units:dict):
		'''
		init
		:param pixel_units: pixel units dict
		'''
		# save params
		s.d = pixel_units
		# default
		s.callbacks = []
		# verify
		s.required_keys = ['force', 'distance', 'momentum']
		extras.validate_config_dict(s.d, {}, s.required_keys)

	def add_callback(s, f) -> None:
		'''
		adds callback `f` to call when updated
		:param f: callback function
			:param: (dict): new pixel units
		:return: None
		'''
		s.callbacks.append(f)

	def scale(s, ratio:float) -> None:
		'''
		scales all the pixel units by `ratio`
		:param ratio: scale ratio
		:return: None
		'''
		s.update({key:n * ratio for key, n in s.d.items()})

	def update(s, pixel_units:dict) -> None:
		'''
		updates pixel units
		:param pixel_units: new pixel units
		:return: None
		'''
		s.d = pixel_units
		[f(s.d) for f in s.callbacks]

	def get(s, unit_type:str):
		'''
		gets a pixel unit
		:param unit_type: unit type
		:return: pixels per 1 unit of `unit type`
		'''
		assert unit_type in s.required_keys
		return s.d[unit_type]


class TextImageUpdater:
	'''
	class for improving text pasting performance
	'''
	def __init__(s, font:image_font.truetype, fg:tuple, bg:tuple, tab_size:int=4):
		'''
		init
		:param font: font object, MUST BE MONOSPACED
		:param fg: foreground color
		:param bg: background color
		:param tab_size: spaces per tab
		'''
		# save args
		s.font = font
		s.fg = fg
		s.bg = bg
		s.tab_size = tab_size
		s.char_size = extras.get_font_size(s.font, 'A')
		# modifiable attrs
		s.prev_lines = [' ']
		s.prev_size = (1, 1)
		s.prev_img = image.new('RGBA', s.char_size)
		s.char_imgs = {}

	def paste(s, main_img:image.Image, text:str, pos:tuple) -> None:
		'''
		pasts text `text` on `img` at `pos`
		:param main_img: image to paste on
		:param text: text string
		:param pos: (X, Y)
		:return: None (modifies image in-place)
		'''
		text = text.replace('\t', ' ' * s.tab_size)# replace tabs with spaces
		lines = text.split('\n')
		# image size in pixels
		size = (max(map(len, lines)) * s.char_size[0], len(lines) * s.char_size[1])
		# get image
		if size == s.prev_img.size:# use previous image
			img = s.prev_img
		else:
			if size[0] > s.prev_img.size[0] or size[1] > s.prev_img.size[1]:# need bigger image
				img = image.new('RGBA', size, (0, 0, 0, 0))
				img.paste(s.prev_img)
			else:# need smaller image
				img = s.prev_img.crop((0, 0) + size)
		# update chars
		for line_n, line in enumerate(lines):# for each line
			if line_n < len(s.prev_lines):# still on text that exists in previous image
				for char_n, char in enumerate(line):
					if char_n < len(s.prev_lines[line_n]):
						if char != s.prev_lines[line_n][char_n]:# characters don't match
							img.paste(s.char_img(char), tuple(map(lambda a, b: a * b, [char_n, line_n], s.char_size)))
					else:
						img.paste(s.char_img(char), tuple(map(lambda a, b: a * b, [char_n, line_n], s.char_size)))
				# put transparent rectangle to cover up any old text that may still show up
				if len(s.prev_lines[line_n]) - len(line) > 0:
					img.paste(image.new('RGBA', (s.char_size[0] * (len(s.prev_lines[line_n]) - len(line)), s.char_size[1]), (0, 0, 0, 0)), (s.char_size[0] * len(line), s.char_size[1] * line_n))
			else:
				for char_n, char in enumerate(line):
					img.paste(s.char_img(char), tuple(map(lambda a, b: a * b, [char_n, line_n], s.char_size)))
		# update previous states
		s.prev_lines = lines
		s.prev_size = (max(map(len, lines)), len(lines))
		s.prev_img = img
		# finally paste onto main image
		main_img.paste(img, pos, mask=img)

	def char_img(s, char:str) -> image.Image:
		'''
		gets image for character or makes one if it dosn't already exist
		:param char: string of length 1
		:return: image
		'''
		assert len(char) == 1, 'character must be a string of length 1'
		assert char != '\n', 'character must not be a newline'
		if char in s.char_imgs.keys():
			return s.char_imgs[char]
		else:
			char_img = image.new('RGB', s.char_size, s.bg)
			drawer = image_draw.Draw(char_img)
			drawer.text((0, 0), char, fill=s.fg, font=s.font)
			s.char_imgs[char] = char_img
			return char_img


class SailRenderer(simulator.SuperSail):
	'''
	class for creating graphics for a sail
	'''
	def __init__(s, static_config:dict, config:dict, pixel_units:CommonPixelUnits):
		'''
		init
		:param static_config:
		:param config:
		:param pixel_units:
		'''
		# save params
		s.pixel_units = pixel_units
		# init superclass
		super().__init__(static_config, config)
		# sheet tension
		s.sheet_tension = s.force.length > 0

	def update(s, config:dict) -> None:
		'''
		updates this sail renderer
		:param config: same as super().load_config
		:return: None
		'''
		s.load_config(config)
		s.sheet_tension = s.force.length > 0

	def render_img(s, img, show_vector:bool, convertor):
		'''
		puts stuff on the image `img`
		:param img: image being rendered
		:param show_vector: whether to show the force vector
		:param convertor: function that turns a local (relative to the boat) position to an image position
		:return: None
		'''
		center = Vec2d(*img.size) / 2
		# drawer
		drawer = image_draw.Draw(img)
		# sail
		drawer.line([convertor([0, s.tack]), convertor(Vec2d(s.foot_len, 0).rotated_degrees(s.angle) + Vec2d(0, s.tack))], fill=(255, 255, 255), width=2)
		# force
		'''TODO: get this from the server
		if show_vector and s.sheet_tension:
			vect_color = [s.force_vector_color, (255, 213, 0)][int(s.turbo_boost)]
			extras.paste_vector_on_img(img, s.curr_center_of_effort, s.force, s.pixel_units.get('distance'), s.pixel_units.get('force'), vect_color, origin=center)
		'''


class SailboatRenderer(simulator.SuperSailboat):
	'''
	sailboat renderer subclass
	'''
	def __init__(s, static_config, config, settings, time_logger:extras.TimeLogger, pixel_units:CommonPixelUnits, font:image_font.ImageFont, username:str):
		'''
		init
		:param static_config: same as superclass
		:param config: see "resources" -> "simulation files" -> "clients" -> "boat" in documentation.html
		:param settings: GUI settings
		:param time_logger: time logger object
		:param pixel_units: pixel units syncing object
		:param font: font to use for boat labels
		:param username: user controlling this boat
		'''
		# save params
		s.font = font
		s.username = username
		# defaults
		s.global_wind = Vec2d(0, 0)
		# settings
		s.update_settings(settings)
		s.pixel_units = pixel_units
		# config update default
		s.config_update_default = copy.deepcopy(config)
		# init superclass
		super().__init__(time_logger, config, static_config)
		# change sails to use SailRenderer instead
		s.sails = {name: SailRenderer(static_conf_dict, config['sails'][name], s.pixel_units) for name, static_conf_dict in s.sails_static.items()}
		s.wind = s.convert_vector(v=s.global_wind, convert_to='local', unit_type='velocity')

	def update_settings(s, d:dict) -> None:
		'''
		updates settings
		:param d: GUI settings
		:return: None
		'''
		s.show_vectors = d['show-vectors']
		s.show_true_wind = d['show-true-wind']
		s.colors = d['colors']
		s.show_boat_labels = d['show-boat-labels']

	def update(s, config:dict, global_wind:Vec2d) -> None:
		'''
		updates from data from the server
		:param config: see Sailboat.serializable.__doc__.return in simulator.py
		:param global_wind: global wind
		:return: None
		'''
		try:
			del s.config_update_default['forces']# to prevent extreme force vectors from showing up on someone else's screen if not in render distance, will be replaced by default
		except KeyError:
			pass
		config = {**copy.deepcopy(s.config_update_default), **config}
		s.config_update_default = copy.deepcopy(config)
		s.setup_config(config, setup_sails=False)
		[sail.update(config['sails'][name]) for name, sail in s.sails.items()]
		s.global_wind = global_wind
		s.wind = s.convert_vector(v=s.global_wind, convert_to='local', unit_type='velocity')

	def render_img(s, img, global_point_to_img_point, main_vector_convertor, main:bool, enabled:bool, project_velocity:bool=False) -> None:
		'''
		puts graphics on `img` to represent the boat
		:param img: image being created
		:param global_point_to_img_point: instance of the method from this class, but may not be from this instance
		:param main_vector_convertor: vector conversion function from main boat
		:param main: whether this instance is the main boat
		:param enabled: whether this boat is enabled (hasn't shipwrecked)
		:param project_velocity: whether to project the boat's velocity on the minimap
		:return: None (modifies image in-place)
		'''
		# conversion functions
		# global pos to image pos
		convertor = lambda pos: global_point_to_img_point(img.size, pos)[0]
		# local pos (this boat) to image pos
		local_convertor = lambda pos: convertor(s.convert_vector(v=pos, convert_to='global', unit_type='pos'))
		# angle conversion
		angle_convertor = lambda vec: main_vector_convertor(v=s.convert_vector(v=vec, convert_to='global', unit_type='angle'), convert_to='local', unit_type='angle')
		# draw color
		boat_color = [(255, 0, 0), (255, 255, 255)][int(enabled)]
		# get center to use as origin
		center = Vec2d(*img.size) / 2
		# init drawer
		drawer = image_draw.Draw(img)
		# perimeter
		draw_coords = list(map(local_convertor, s.perimeter))
		# draw
		drawer.line(draw_coords + draw_coords[:1], fill=boat_color, width=2)
		# paste rudder image
		drawer.line([local_convertor([0, s.rudder_pivot]), local_convertor(Vec2d(s.rudder_len, 0).rotated_degrees(s.rudder_angle) + Vec2d(0, s.rudder_pivot))], fill=boat_color, width=2)
		# paste sail images
		for sail in s.sails.values():
			sail.render_img(img, s.show_vectors, local_convertor)
		# wind vectors
		if main:
			# apparent
			if s.wind.length > 0:
				extras.paste_vector_on_img(img, -(s.wind.scale_to_length(center.length)), s.wind.scale_to_length(center.length - (min(img.size) * 0.3333)), color=s.colors['app-wind'], width=20, origin=center, draw_arrow=False)
			# true
			if s.show_true_wind and s.global_wind.length > 0:
				disp_global_wind = s.convert_vector(v=s.global_wind, convert_to='local', unit_type='angle')
				extras.paste_vector_on_img(img, -(disp_global_wind.scale_to_length(center.length)), disp_global_wind.scale_to_length(center.length - (min(img.size) * 0.3333)), color=s.colors['true-wind'], width=20, origin=center, draw_arrow=False)
		# paste vectors
		if s.show_vectors:
			tmp_force_vectors = {key: angle_convertor(force[1]) for key, force in s.forces.items()}
			# sail force
			extras.paste_vector_on_img(img, start=local_convertor(s.forces['sails-total'][0]), v=tmp_force_vectors['sails-total'], pixels_per_unit_vec=s.pixel_units.get('force'), color=s.colors['total-sail-force'], reverse_y_start=False)
			# drag force
			extras.paste_vector_on_img(img, start=local_convertor(s.forces['hull-water-drag'][0]), v=tmp_force_vectors['hull-water-drag'], pixels_per_unit_vec=s.pixel_units.get('force'), color=s.colors['drag-force'], reverse_y_start=False)
			# velocity
			extras.paste_vector_on_img(img, start=convertor(s.pos), v=angle_convertor(s.local_velocity()), pixels_per_unit_vec=s.pixel_units.get('momentum'), color=s.colors['velocity'], reverse_y_start=False)
			# rudder force
			extras.paste_vector_on_img(img, start=local_convertor(s.forces['rudder'][0]), v=tmp_force_vectors['rudder'], pixels_per_unit_vec=s.pixel_units.get('force'), color=s.colors['rudder-force'], reverse_y_start=False)
			# Total Force of Acceleration
			extras.paste_vector_on_img(img, start=local_convertor(s.forces['total'][0]), v=tmp_force_vectors['total'], pixels_per_unit_vec=s.pixel_units.get('force'), color=s.colors['total-acceleration-force'], reverse_y_start=False)
		# boat label
		if s.show_boat_labels:
			if s.max_hull_durability == -1:
				ratio = 1
			else:
				ratio = s.hull_durability / s.max_hull_durability
			text = f'{s.username}\n{str(round(ratio * 100))}%'
			char_size = extras.get_font_size(s.font, 'A')
			text_size = (char_size[0] * max([len(line) for line in text.split('\n')]), char_size[1] * len(text.split('\n')))
			text_pos = [p - (ts / 2) for p, ts in zip(local_convertor([0, 0]), text_size)]# center text on the boat's center
			if point_on_img(img.size, local_convertor([0, 0])):
				drawer.text(text_pos, text, fill='red', font=s.font, align='center')

	def local_point_to_image_point(s, img_size:tuple, pos, clip_pos:bool=False) -> tuple:
		'''
		converts boat relative position `pos` to PIL-style position (reversed Y) for display on the main image
		:param img_size: size of image
		:param pos: position
		:param clip_pos: weather to use max(min( , ), 0) to limit the output position coords
		:return: tuple:
			* position coord tuple (PIL-style, in pixels)
			* (bool): whether the point is on the image
		'''
		# convert pos to list
		pos = extras.convert_pos(pos, list)
		# convert to pixels
		pos = [(c * s.pixel_units.get('distance')) for c in pos]
		# add center of the image
		pos = [int(c + (size / 2)) for size, c in zip(img_size, pos)]
		# change Y
		pos[1] = img_size[1] - pos[1]
		# test if inside
		inside = point_on_img(img_size, pos)
		# clip
		if clip_pos:
			pos = [max(0, min(_s - 1, c)) for _s, c in zip(img_size, pos)]
		return tuple(pos), inside

	def global_point_to_img_point(s, img_size:tuple, pos) -> tuple:
		'''
		converts
		:param img_size: size of image
		:param pos: global position
		:return: tuple:
			* PIL-compatible coordinate tuple
			* (bool): whether the point is on the image
		'''
		return s.local_point_to_image_point(img_size, s.convert_vector(v=pos, convert_to='local', unit_type='pos'))


class MapRenderer(simulator.SuperMap):
	'''
	map renderer subclass
	'''
	def __init__(s, config, boat:SailboatRenderer, time_logger:extras.TimeLogger, settings:dict, pixel_units:CommonPixelUnits):
		'''
		init
		:param config: same as superclass
		:param boat: main boat renderer object
		:param time_logger: time logger object
		:param settings: GUI settings
		:param pixel_units: pixel units syncing object
		'''
		# save params
		s.boat = boat
		s.time_logger = time_logger
		s.pixel_units = pixel_units
		# settings
		s.update_settings(settings)
		# init superclass
		super().__init__(config)
		# constants
		ratio = s.size[1] / s.size[0]

	def update_settings(s, d:dict) -> None:
		'''
		updates settings
		:param d: GUI settings
		:return: None
		'''
		s.floodfill_land = d['floodfill-land']
		s.show_end_flag = d['show-end-flag']
		s.colors = d['colors']

	def render_main(s, img) -> None:
		'''
		renders the lowest level of the image (the map) for the maine image
		:param img: image to paste graphics on
		:return: None (modifies image in-place)
		'''
		s.paste_on_img(img, 'local')

	def render_minimap(s, width:int) -> image.Image:
		'''
		renders the first layer of the minimap image
		:param width: minimap width (pixels)
		:return: minimap image
		'''
		# create image
		scale = s.size[0] / width
		img = image.new('RGB', tuple([int(n / scale) for n in s.size]), tuple(s.colors['ocean']))
		# draw map
		s.paste_on_img(img, 'global')
		return img

	def paste_on_img(s, img:image.Image, mode:str):
		'''
		pastes this map on `img`
		:param img: image to paste on
		:param mode: can be 'global' (for minimap), or 'local' (main view)
		:return: converter function
		'''
		# assertions
		assert mode in ['global', 'local']
		drawer = image_draw.Draw(img)
		# initial calculations
		feet_per_pixel = s.size[0] / img.size[0]
		if mode == 'global':# convertor will be a function that turns a global position into an image position
			tmp = lambda pos: tuple([int(n / feet_per_pixel) for n in pos])
			convertor = lambda pos: [tmp(pos)[0], img.size[1] - tmp(pos)[1]]# reverses Y
		else:
			convertor = lambda pos: s.boat.global_point_to_img_point(img.size, pos)[0]
		# layer 1: the map
		for landmass in s.landmasses:
			coastline = Polygon([convertor(pos) for pos in landmass['coords'].exterior.coords])
			rep_point = extras.convert_pos(convertor(landmass['rep-point'].coords[0]), tuple)
			draw_coords = list(coastline.exterior.coords)
			s.time_logger.start_log('coastlines')
			drawer.line(draw_coords + [draw_coords[-1]], fill=(255, 255, 255), width=1)
			s.time_logger.stop_log('coastlines')
			# TODO: improve performance
			if point_on_img(img.size, rep_point) and (s.floodfill_land or mode == 'global'):
				s.time_logger.start_log('rep points')
				image_draw.floodfill(img, rep_point, tuple(landmass['color']))
				s.time_logger.stop_log('rep points')
		# checkered flag
		if s.show_end_flag:
			flag_img = extra_imgs['checkered-flag-small']
			flag_pos = convertor(list(s.end))
			if mode == 'local' and not point_on_img(img.size, flag_pos):
				# get angle of the end relative to the center and scale it to a fixed length
				angle = Vec2d(flag_pos[0] - (img.size[0] / 2), (img.size[1] / 2) - flag_pos[1]).angle_degrees
				flag_pos = list(Vec2d(min(img.size) * 0.375, 0).rotated_degrees(angle))
				extras.paste_vector_on_img(img, Vec2d(*flag_pos), Vec2d(36, 0).rotated_degrees(angle), color=(0, 255, 0), origin=Vec2d(*img.size) / 2)
				# add center
				flag_pos = [flag_pos[0] + (img.size[0] / 2), (img.size[1] / 2) - flag_pos[1]]
			# add height of image and make sure that they are ints
			flag_pos = [int(flag_pos[0]), int(flag_pos[1] - flag_img.size[1])]
			# paste
			img.paste(im=flag_img, box=flag_pos, mask=flag_img)
		return convertor


class Renderer:
	'''
	class for rendering graphics for the client process
	'''
	def __init__(s,
		img_label:tk.Label,
		frame:tk.Frame,
		map_config:dict,
		client_data:dict,
		settings:dict,
		alert:extras.Alert,
		time_logger:extras.TimeLogger,
		pixel_units:CommonPixelUnits,
		size:tuple,
		username:str,
		sheeting_angle_update_callback,
		rudder_control:extras.RudderInput):
		'''
		init
		:param img_label: tkinter image label to use
		:param frame: tkinter frame to use for other widgets
		:param map_config: see "resources" -> "map files" in documentation.html
		:param client_data: see simulator.Simulator.serializable('client')
		:param settings: GUI settings dict
		:param alert: alert object
		:param time_logger: time logger object for the client
		:param pixel_units: common pixel units object
		:param size: image size
		:param username: this client's username
		:param sheeting_angle_update_callback: callback function, should be main.SimClient.set_sheeting_angle
		:param rudder_control: rudder controller object
		'''
		# save params
		s.img_label = img_label
		s.frame = frame
		s.alert = alert
		s.time_logger = time_logger
		s.pixel_units = pixel_units
		s.username = username
		s.sheeting_angle_update_callback = sheeting_angle_update_callback
		s.rudder_control = rudder_control
		# tk vars
		s.hide_graphics = tk.BooleanVar()# hide all of the graphics except for the boat and map render functions
		s.hide_graphics.set(False)
		s.project_velocity = tk.BooleanVar()
		s.project_velocity.set(False)
		s.global_wind_vect = Vec2d(0, 0)
		# defaults
		s.scale_padding = 10
		s.boat_durability_bar_width = 102
		s.rudder_control_status = 0
		s.autopilot_enabled = False
		s.global_time = 0
		s.time_logger_results = ''
		s.client_fps = 1
		s.server_fps = 1
		# create a boat renderer for each client on the server
		s.boats = {}
		s.boat_states = {}
		for client_username, client in client_data.items():
			s.boats[client_username] = SailboatRenderer(client['boat-static-config'], client['boat'], settings, s.time_logger, s.pixel_units, mono_font, client_username)
			s.boat_states[client_username] = client['enabled']
		s.main_boat = s.boats[s.username]
		main_client_config = client_data[s.username]
		s.tracer_lst = main_client_config['tracer-lst']
		s.autopilot_config = main_client_config['autopilot']
		s.autopilot_target_pos = s.autopilot_config['target-pos']
		s.personal_timer = main_client_config['timer']['t']
		# setup GUI
		s.create_gui()
		# map renderer
		s.map = MapRenderer(map_config, s.main_boat, time_logger, settings, s.pixel_units)
		# set image size
		s.set_img_size(size)
		# settings
		s.update_settings(settings)
		# load state data
		s.setup_state_data(main_client_config)

	def update_settings(s, d:dict) -> None:
		'''
		loads settings from settings.json
		:param d: GUI settings
		:return: None
		'''
		s.colors = d['colors']
		s.floodfill_land = d['floodfill-land']
		s.show_timer = d['show-timer']
		s.show_tracer = d['show-tracer']
		s.show_end_flag = d['show-end-flag']
		s.show_performance = d['show-performance']
		# status text updater
		s.status_text_updater = TextImageUpdater(mono_font, s.colors['text-fg'], s.colors['text-bg'])
		# update map and boat
		try:
			[boat.update_settings(d) for _, boat in s.boats.items()]
			s.map.update_settings(d)
		except AttributeError:
			pass
		# minimap background
		s.render_minimap_background()

	def create_gui(s) -> None:
		'''
		sets up the GUI for graphics settings
		:return: None
		'''
		curr_row = 0
		# input 0: minimap width scale
		tk.Label(s.frame, text='Minimap width').grid(row=curr_row, column=0)
		s.minimap_width_scale = tk.Scale(s.frame, from_=1, to=100, command=lambda _: s.render_minimap_background(), orient=tk.HORIZONTAL)
		s.minimap_width_scale.grid(row=curr_row, column=1)
		s.minimap_width_scale.bind('<Button-1>', lambda _: s.minimap_width_scale.focus_set())
		# input 1: hide graphics checkbutton
		curr_row += 1
		tk.Checkbutton(s.frame, text='Hide extra graphics', variable=s.hide_graphics).grid(row=curr_row, column=1)
		# input 2: project velocity checkbutton, TODO: implement
		curr_row += 1
		tk.Checkbutton(s.frame, text='Project velocity', variable=s.project_velocity).grid(row=curr_row, column=1)
		# input 3: sheeting angles
		s.sheeting_sliders = {}
		s.sheet_slack_labels = {}# sail name:(bool) weather the sail's sheet is slack
		for name, sail in s.main_boat.sails.items():
			curr_row += 1
			tmp_frame = tk.Frame(s.frame)
			tmp_frame.grid(row=curr_row, column=0)
			tk.Label(tmp_frame, text=f'Sheeting angle {name}').grid(row=0, column=0)
			s.sheeting_sliders[name] = tk.Scale(s.frame, from_=0, to=90, command=(lambda name: lambda value_str: s.sheeting_angle_update_callback(name, int(value_str)))(name), orient=tk.HORIZONTAL, tickinterval=90, takefocus=True)
			s.sheeting_sliders[name].grid(row=curr_row, column=1)
			s.sheeting_sliders[name].bind('<Button-1>', (lambda scale: lambda _: scale.focus_set())(s.sheeting_sliders[name]))# see stackoverflow.com/questions/2295290
			# set slider to what is stored in the sail object
			s.sheeting_sliders[name].set(sail.sheeting_angle)
			# label to show when the sheet is slack
			s.sheet_slack_labels[name] = tk.Label(tmp_frame, text='', fg='red')
			s.sheet_slack_labels[name].grid(row=1, column=0)

	def set_sheeting_slider_states(s, state:bool) -> None:
		'''
		for when the boat is reset or shipwrecked, enable or disable all sheeting sliders
		:param state: bool
		:return: None
		'''
		[slider.config(state=('disabled', 'normal')[int(state)]) for _, slider in s.sheeting_sliders.items()]

	def setup_state_data(s, main_client_config:dict) -> None:
		'''
		used in __init__ and after a reset to load the GUI with start data from the server
		:param main_client_config: client config for this client
		:return: None
		'''
		# sheeting sliders
		sails = main_client_config['boat']['sails']
		[slider.set(sails[name]['sheeting-angle']) for name, slider in s.sheeting_sliders.items()]

	def update(s, server_response:dict, autopilot_enabled:bool, time_logger_results:str, client_fps:float, rudder_control_status:int=0) -> None:
		'''
		updates the renderer status
		:param server_response: response from server
		:param autopilot_enabled: whether the autopilot is enabled
		:param time_logger_results: results from previous frame
		:param client_fps: the client's framerate
		:param rudder_control_status: integer representing the rudder control: 0: don't show, 1: show but not being used, 2: being used
		:return: None
		'''
		# save params
		boat_updates = server_response['clients']
		s.autopilot_target_pos = boat_updates[s.username]['autopilot']['target-pos']
		s.personal_timer = boat_updates[s.username]["general"]["timer"]
		s.global_time = server_response['global-data']['timer']
		s.server_fps = server_response['global-data']['FPS']
		s.global_wind_vect = Vec2d(*server_response['global-data']["wind"])
		s.autopilot_enabled = autopilot_enabled
		s.time_logger_results = time_logger_results
		s.client_fps = client_fps
		s.rudder_control_status = rudder_control_status
		# update boat renderers
		for username, client_data in boat_updates.items():
			s.boats[username].update(client_data['boat'], s.global_wind_vect)
			s.boat_states[username] = client_data['general']['enabled']
		# update tracer list
		# TODO
		# update sheet slack labels
		for name, wdgt in s.sheet_slack_labels.items():
			wdgt.config(text='(slack)' * int(not s.main_boat.sails[name].sheet_tension))

	def render_img(s) -> None:
		'''
		creates complete image to be displayed on the GUI
		layers:
			1: map
			2: boats
			3: status graphics and text
			4: alert
			5: FPS
			6: scale
			7: mouse rudder control
		:return: None
		'''
		s.img = image.new('RGB', s.size, (128, 128, 128))
		drawer = image_draw.Draw(s.img)
		# layer 1: the map
		s.time_logger.start_log('map')
		s.map.render_main(s.img)
		s.time_logger.stop_log('map')
		# layer 2: boats
		s.time_logger.start_log('boats')
		[boat.render_img(img=s.img, global_point_to_img_point=s.main_boat.global_point_to_img_point, main_vector_convertor=s.main_boat.convert_vector, main=username == s.username, enabled=s.boat_states[username]) for username, boat in s.boats.items()]
		s.time_logger.stop_log('boats')
		# layer 3: other stuff to make it look good
		if not s.hide_graphics.get():
			# minimap
			s.time_logger.start_log('minimap')
			curr_minimap_img = copy.deepcopy(s.minimap_bg_img)
			minimap_size = s.minimap_bg_img.size
			minimap_drawer = image_draw.Draw(curr_minimap_img)
			# boat path tracer
			if s.show_tracer:
				coords = [tuple(s.global_pos_to_minimap_pos(pos)) for pos in s.tracer_lst + [list(s.main_boat.pos)]]
				minimap_drawer.line(coords, s.colors['tracer-path'], width=1)
			# paste arrow icons to represent the boats
			for name, boat in s.boats.items():
				if name == s.username:
					pointer = 'pointer-blue'
				else:
					if s.boat_states[name]:
						pointer = 'pointer-green'
					else:
						pointer = 'pointer-red'
				rotated_boat_arrow = extra_imgs[pointer].rotate(boat.angle)
				arrow_pos = [c - int(_s / 2) for c, _s in zip([int(n) for n in s.global_pos_to_minimap_pos(list(boat.pos))], rotated_boat_arrow.size)]
				curr_minimap_img.paste(rotated_boat_arrow, tuple(arrow_pos), rotated_boat_arrow)
			# autopilot target position
			if s.autopilot_enabled:
				extras.dot_on_img(curr_minimap_img, s.global_pos_to_minimap_pos(s.autopilot_target_pos), 6, (255, 0, 0))
			# paste minimap image
			s.img.paste(curr_minimap_img, (s.size[0] - minimap_size[0], 0))# top-right corner
			s.time_logger.stop_log('minimap')
			# compass
			# paste blank compass image
			s.time_logger.start_log('compass')
			s.img.paste(extra_imgs['compass-blank'], (0, 0), None)
			# paste needle on compass
			rot_compass = extra_imgs['compass-needle'].rotate(-(s.main_boat.angle - 90) % 360, expand=True)
			s.img.paste(rot_compass, tuple([int(40 - (n / 2)) for n in rot_compass.size]), rot_compass)
			s.time_logger.stop_log('compass')
			# global wind indicator
			# paste blank compass image
			s.time_logger.start_log('wind-indicator')
			s.img.paste(extra_imgs['compass-blank'], (80, 0), None)
			# paste wind arrow on dial
			rot_arrow = extra_imgs['wind-arrow'].rotate((s.main_boat.convert_vector(v=s.global_wind_vect, convert_to='local', unit_type='angle').angle_degrees + 90) % 360, expand=True)
			s.img.paste(rot_arrow, tuple([int(offset - (n / 2)) for n, offset in zip(rot_arrow.size, [120, 40])]), rot_arrow)
			s.time_logger.stop_log('wind-indicator')
			# status text
			s.time_logger.start_log('text')
			status_text = f'wind: {str(round(s.global_wind_vect.length, 2))} m/sec\n' +\
				f'apparent wind: {str(round(s.main_boat.wind.length, 2))} m/sec\n' +\
				f'position: {str([round(n, 2) for n in list(s.main_boat.pos)])}\n' +\
				f'velocity: {str([round(n, 2) for n in list(s.main_boat.velocity)])}\n' +\
				f'local velocity: {str([round(n, 2) for n in list(s.main_boat.local_velocity())])}\n' +\
				f'speed: {str(round(s.main_boat.velocity.length, 2))}\n' +\
				f'leeway: {str(round(s.main_boat.leeway_angle, 1))} deg\n' +\
				f'angular velocity: {str(round(s.main_boat.angular_velocity, 1))} deg/sec\n' +\
				f'boat angle: {str(round(s.main_boat.angle, 1))}\n' +\
				f'rudder source: {str(s.rudder_control.curr_input)}'
			if s.show_timer:
				status_text += f'\nsimulation timer: {dt.timedelta(seconds=round(s.global_time, 2))}\n' +\
					f'personal timer: {dt.timedelta(seconds=round(s.personal_timer, 2))}'
			if s.show_performance:
				status_text += '\nPerformance:\n' + s.time_logger_results
			s.status_text_updater.paste(s.img, status_text.strip().replace('\n\n', '\n'), (0, 80))
			s.time_logger.stop_log('text')
			# boat durability progress bar
			width = s.boat_durability_bar_width
			prog_bar = image.new('RGB', (width, 12), (255, 255, 255))
			prog_bar.paste(image.new('RGB', (width - 2, 10), (0, 0, 0)), (1, 1))
			if s.main_boat.max_hull_durability == -1:
				ratio = 1
			else:
				ratio = s.main_boat.hull_durability / s.main_boat.max_hull_durability
			prog_bar.paste(image.new('RGB', (max(int(ratio * (width - 2)), 0), 10), (0, 255, 0)), (1, 1))
			s.img.paste(prog_bar, (int((s.size[0] / 2) - (width / 2)), s.size[1] - 12))
		# layer 4: alert
		s.time_logger.start_log('alert text')
		s.alert.render_img(s.img)
		s.time_logger.stop_log('alert text')
		# layer 5: FPS
		extras.paste_text(s.img, (0, s.size[1] - 24), f'FPS: {str(round(s.client_fps, 1))}', mono_font, fg=s.colors['text-fg'], bg=s.colors['text-bg'])
		extras.paste_text(s.img, (0, s.size[1] - 12), f'server FPS: {str(round(s.server_fps, 1))}', mono_font, fg=s.colors['text-fg'], bg=s.colors['text-bg'])
		# layer 6: scale
		s.time_logger.start_log('scale')
		# calculate length to use (I am very proud of this)
		MSDs = [1, 1.5, 2, 3, 5, 7.5]# Most Significant Digits
		max_length_px = int((s.size[0] / 2) - ((s.boat_durability_bar_width / 2) + (s.scale_padding * 2)))
		max_length = max_length_px / s.pixel_units.get('distance')
		pv = math.floor(math.log(max_length, 10))# place-value exponent
		for MSD in reversed(MSDs):
			length = 10**pv * MSD
			if length <= max_length:
				break
		# display
		length_px = length * s.pixel_units.get('distance')
		left_end_x = s.size[0] - (length_px + s.scale_padding)
		base_y = s.size[1] - 14
		drawer.line([(left_end_x, base_y - 5), (left_end_x, base_y), (s.size[0] - s.scale_padding, base_y), (s.size[0] - s.scale_padding, base_y - 5)], fill=(255, 255, 255), width=1)
		text = f'{str(length)} meters'
		text_size = extras.get_font_size(mono_font, text)
		text_x = int(s.size[0] - (length_px / 2) - s.scale_padding - (text_size[0] / 2))
		drawer.text((text_x, s.size[1] - text_size[1] - 1), text, fill=(255, 255, 255), font=mono_font)
		s.time_logger.stop_log('scale')
		# layer 7: mouse rudder control
		if s.rudder_control_status >= 1:
			s.time_logger.start_log('mouse rudder control')
			l = s.img_rudder_ctrl_box# min X, min Y, max X, max Y
			# draw border
			drawer.line([(l[0], l[1]), (l[2], l[1]), (l[2], l[3]), (l[0], l[3]), (l[0], l[1])], (255, 0, 0), s.rudder_control_status)
			s.time_logger.stop_log('mouse rudder control')
		# update image to GUI
		s.time_logger.start_log('creating PhotoImage')
		s.curr_tk_img = image_tk.PhotoImage(s.img)
		s.time_logger.stop_log('creating PhotoImage')
		s.time_logger.start_log('updating label')
		s.img_label.config(image=s.curr_tk_img)
		s.time_logger.stop_log('updating label')

	def render_minimap_background(s) -> None:
		'''
		creates background image to use for the minimap
		:return: None
		'''
		# render minimap background
		s.minimap_bg_img = s.map.render_minimap(int(s.minimap_width_scale.get()))

	def global_pos_to_minimap_pos(s, pos:list) -> list:
		'''
		converts a global position to a PIL-style position on the minimap
		:param pos: global coords list
		:return: PIL-style coords list
		'''
		# change to pixels
		scale = s.map.size[0] / s.minimap_bg_img.size[0]
		pos = [n / scale for n in pos]
		# reverse Y
		pos[1] = (s.map.size[1] / scale) - pos[1]
		# make into integers
		pos = map(int, pos)
		return pos

	def img_minimap_to_global_pos(s, pos:list) -> tuple:
		'''
		converts a PIL-style position on the main image to a global position displayed in the corresponding position displayed on the minimap
		:param pos: position coord list
		:return: tuple:
			* (bool): whether the position is on the minimap
			* global position or None
		'''
		# determine if the position is on the minimap
		if pos[0] >= s.size[0] - s.minimap_bg_img.size[0] and pos[1] < s.minimap_bg_img.size[1]:
			pos[0] -= s.size[0] - s.minimap_bg_img.size[0]
			ratio = s.map.size[0] / s.minimap_bg_img.size[0]
			# reverse Y
			pos = [pos[0], s.minimap_bg_img.size[1] - pos[1]]
			# change scale
			global_pos = [c * ratio for c in pos]
			return True, global_pos
		return False, None

	def set_img_size(s, size:tuple) -> None:
		'''
		sets new image render size
		:param size: new size list
		:return: None
		'''
		if hasattr(s, 'size'):
			if size == s.size:
				return
			# min size ratio
			min_size_ratio = min(size) / min(s.size)
			# old max minimap width
			old_max_minimap_width = int(min(s.size[0], s.size[1] / (s.map.size[1] / s.map.size[0])))
			# set first time flag
			first_time = False
		else:
			min_size_ratio = 1
			first_time = True
		# rudder control box
		w, h = size
		s.img_rudder_ctrl_box = [50, h - 150, w - 50, h - 50]
		# minimap size
		s.max_minimap_width = int(min(size[0], size[1] / (s.map.size[1] / s.map.size[0])))
		if first_time:
			width = int(max(1, int(s.max_minimap_width / 3)))
		else:
			width = int(max(1, int(s.minimap_bg_img.size[0] * (s.max_minimap_width / old_max_minimap_width))))
		s.minimap_width_scale.config(to=s.max_minimap_width)
		s.minimap_width_scale.set(width)
		s.render_minimap_background()
		# save new size
		s.size = size
		# pixel units
		s.pixel_units.update({key: n * min_size_ratio for key, n in s.pixel_units.d.items()})


def generate_compass_img_blank() -> image.Image:
	'''
	NOTE: this was used once to generate imgs/compass-blank.png
	generates a blank compass image to be used for the whole rest of the program with size (80, 80)
	:return: image
	'''
	size = 80
	img = image.new('RGB', (size, size), (255, 255, 255))
	draw = image_draw.Draw(img)
	center = int(size/2)
	circle_radias = int((size-16)/2)
	draw.arc([(8, 8), tuple([int((circle_radias*2)+7)]*2)], 0, 360, (0, 0, 0), 1)
	for tick_len, tick_count in [(16, 4), (8, 8), (4, 16)]:
		for angle_int in range(0, 720, int(360/(tick_count/2))):
			angle = angle_int/2
			radias_min = circle_radias - (tick_len / 2)
			radias_max = circle_radias + (tick_len / 2)
			start = [math.cos(angle * extras.TC) * radias_min, math.sin(angle * extras.TC) * radias_min]
			end = [math.cos(angle * extras.TC) * radias_max, math.sin(angle * extras.TC) * radias_max]
			draw.line([n+center for n in start+end], (0, 0, 0), 1)
	return img

def point_on_img(size:tuple, pos) -> bool:
	'''
	determines of `point` is on an image with `size`
	:param size: image size
	:param pos: position
	:return: bool
	'''
	pos = tuple(extras.convert_pos(pos, list))
	return not (False in [0 <= c < s for c, s in zip(pos, size)])

def get_font_size(font, string):
	font_bb = font.getbbox(string)
	return (font_bb[2] - font_bb[0], font_bb[3] - font_bb[1] + 2)

# load images
os.chdir(extras.imgs_dir)
extra_imgs = {fn.split('.')[0]: image.open(fn) for fn in os.listdir(extras.imgs_dir) if fn.lower() != '.ds_store'}
# font
os.chdir(extras.base_dir)
mono_font = image_font.truetype('VeraMono.ttf', 12)
