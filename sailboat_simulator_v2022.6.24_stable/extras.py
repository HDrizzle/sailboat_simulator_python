#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  extras.py
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
import copy
import math, os, json, time, socket, threading, webbrowser
import datetime as dt

# third-party, from PyPi
import tkinter as tk
from pymunk.vec2d import Vec2d# very usefull
from shapely.geometry import *
from PIL import Image as image
from PIL import ImageFont as image_font
from PIL import ImageDraw as image_draw

# from CWD
try:
	from GS_timing import micros
except Exception:
	micros = lambda: time.time_ns() / 1000
	print('INFO: could not import GS_timing, using time.time_ns() instead')


# classes
class Timer:
	def __init__(s, config:dict={}):
		'''
		class to record the simulation time, supports sim/real time ratios
		'''
		default_config = {'t': 0, 'running': False, 'ratio': 1}
		config = {**default_config, **config}
		s.reset()
		s.set_ratio(config['ratio'])
		s.total = config['t']
		if config['running']:
			s.start()

	def __str__(s) -> str:
		'''
		string representation of self
		:return: formatted time string
		'''
		return str(dt.timedelta(seconds=round(s.result(), 2)))

	def set_ratio(s, ratio:float=1) -> None:
		'''
		NOTE: this should not be called constantly
		sets the time ratio
		:param ratio: sim/real time ratio
		:return: None
		'''
		# assert
		assert ratio >= 0, 'time ratio must be >= 0'
		was_running = s.running
		s.stop()
		s.ratio = ratio
		if was_running:
			s.start()

	def reset(s) -> None:
		'''
		resets the timer
		:return: None
		'''
		s.total = 0
		s.running = False
		s.start_t = None

	def set(s, t:float) -> None:
		'''
		sets the timer value to `t`
		:param t: time to set timer to
		:return: None
		'''
		s.total = t
		if s.running:
			s.start_t = time.time()

	def start(s) -> None:
		'''
		starts the timer
		:return: None
		'''
		# check if stoped, otherwise do nothing
		if not s.running:
			s.start_t = time.time()
			s.running = True

	def stop(s) -> None:
		'''
		stops the timer
		:return: None
		'''
		# check if running, otherwise do nothing
		if s.running:
			s.total += (time.time() - s.start_t) * s.ratio
			s.running = False

	def result(s) -> float:
		'''
		gets the current time being recorded
		:return: time (secs)
		'''
		return_t = s.total
		if s.running:
			return_t += (time.time() - s.start_t) * s.ratio
		return return_t

	def serializable(s) -> dict:
		'''
		:return: JSON serializable dict to represent this instance
		'''
		return {
			't': s.result(),
			'running': s.running,
			'ratio': s.ratio
		}


class Alert:
	def __init__(s):
		'''
		class for storing alerts for space_class
		'''
		os.chdir(base_dir)
		s.font = image_font.truetype('VeraMono.ttf', 24)
		s.alerts = []# text, fill color, time to delete (could be None)

	def __contains__(s, item:str) -> bool:
		'''
		checks if the string `item` is in alerts list
		:param item: string to check for
		:return: boolean
		'''
		return True in [item == l[0] for l in s.alerts]

	def update(s) -> None:
		'''
		NOTE: does not need to be called externaly
		deletes all alerts that have an old timestamp
		:return: None
		'''
		i = 0
		while i < len(s.alerts):
			if (s.alerts[i][2] != None) and (s.alerts[i][2] <= time.time()):
				del s.alerts[i]
				i -= 1
			i += 1

	def render_img(s, img) -> None:
		'''
		draws text on `img`
		:param img: image to paste alerts on
		:return: None (modifies image in-place)
		'''
		s.update()
		size = get_font_size(s.font, '\n'.join([l[0] for l in s.alerts]))
		y = (img.size[1] / 2) - (size[1] / 2)
		for i, alert in enumerate(s.alerts):
			curr_pos = [int((img.size[0] / 2) - (get_font_size(s.font, alert[0])[0] / 2)), int(y + (i * 24))]
			paste_text(img, curr_pos, alert[0], s.font, alert[1])

	def add(s, text:str, color:tuple, t:float, avoid_dupe:bool=True) -> None:
		'''
		adds alert
		:param text: alert text
		:param color: alert color
		:param t: time to display alert, None is forever
		:param avoid_dupe: weather to avoid adding duplicates of `text`
		:return: None
		'''
		color = tuple(color)
		if t is None:
			s.alerts.append([text, color, None])
		else:
			if avoid_dupe and text in s:
				for i, l in enumerate(s.alerts):
					if l[0] == text:
						s.alerts[i][2] = time.time() + t
						s.alerts[i][1] = color
			else:
				s.alerts.append([text, color, time.time() + t])

	def clear(s) -> None:
		'''
		clears all alerts
		:return: None
		'''
		s.alerts = []


class TimeLogger:
	def __init__(s):
		'''
		class for keeping track of how much time is used by various functions or processes
		'''
		# s.d = {'<process name>':{'times':[<start time1>, <stop time1>, ...], 'sub':<copies of s.curr_d>}, ...}
		s.d = {}
		# s.curr_d is processes being logged at the current level
		s.curr_d = s.d
		# curr_logging is used for copying time from an inner process to an outer process
		s.call_stack = []# processes that are currently being logged, ['<process>', '<sub-process>']

	def __str__(s):
		'''
		create a string representation of self
		:return: string
		'''
		return s.node_string(s.d)

	def start_log(s, p_name) -> None:
		'''
		starts log for process with time and process name
		:param p_name: process name
		:return: None
		'''
		if p_name in s.curr_d.keys():
			s.curr_d[p_name]['times'].append(t())
		else:
			s.curr_d[p_name] = {'times':[t()], 'sub':{}}
		s.curr_d = s.curr_d[p_name]['sub']
		s.call_stack.append(p_name)

	def stop_log(s, p_name) -> None:
		'''
		stops log for process with time and process name
		:param p_name: process name
		:return: None
		'''
		del s.call_stack[-1]
		s.curr_d = recursive_index(s.d, [[s.call_stack[int(i/2)], 'sub'][i % 2] for i in range(len(s.call_stack)*2)])
		if p_name in s.curr_d.keys():
			if len(s.curr_d[p_name]['times']) % 2 == 0:
				raise RuntimeError(f'stop_log() was called without the process: {p_name} logged as running')
			else:# everything is ok
				s.curr_d[p_name]['times'].append(t())
		else:
			raise RuntimeError(f'stop_log() was called before start_log() with the process name: {p_name}')

	def clear(s, p_name=None) -> None:
		'''
		clears a process p_name at the current level. if it is None it clears everything
		:param p_name: process name
		:return: None
		'''
		if p_name == None:
			s.d = {}
			s.curr_d = s.d
			s.call_stack = []
		else:
			try:
				s.curr_d[p_name] = {'times':[], 'sub':{}}
			except KeyError:
				raise KeyError('clear() was called with a process name that does not exist')

	def get_times(s, d) -> dict:
		'''
		gets the total runtimes for all processes for `d`
		:param d: dict to use
		:return: dictionary of each process name and it's total runtime
		'''
		temp_d = {}
		for key in d.keys():
			lst = d[key]['times']
			temp_d[key] = sum([lst[i]-lst[i+1] for i in range(int(len(lst)/2))])
		return temp_d

	def node_string(s, d:dict, indent:int=0, indent_s:str='  ', formatter=lambda pcnt, name: (f'{str(int(pcnt))}%: '.rjust(6, '0')) + name, sorted_:bool=False) -> str:
		'''
		creates a string representation of the self
		:param d: dict to use
		:param indent: current indent (this method is recursive)
		:param indent_s: indent string
		:param formatter: formatter function that accepts: pcnt:(percent of the time for `name`)float, name:(process name)str
		:param sorted_: weather to sort the results by runtime
		:return: user-friendly string
		'''
		times = s.get_times(d)
		total_time = sum([n for _, n in times.items()])
		curr_indent_s = indent_s*indent
		string = ''
		for key in [d.keys(), sorted(d.keys(), key=lambda key:times[key])][int(sorted_)]:
			if len(d[key]['times']) % 2 != 0:
				raise RuntimeError(f'string_to_print() was called with an odd number of log times for the process name: {key}')
			curr_time = times[key]
			try:
				pcnt = (curr_time / total_time) * 100
			except ZeroDivisionError:
				pcnt = 100
			curr_s = curr_indent_s + formatter(pcnt, key) + '\n'
			curr_s += s.node_string(d[key]['sub'], indent+1, indent_s)
			string += curr_s
		return string


class SocketServer:
	def __init__(s, callback, recv_socket:int, ip:str='127.0.0.1', validate_as_json:bool=True):
		'''
		some code copied from: realpython.com/python-sockets/
		socket server handler
		:param callback: callback function for when data is received
			:param 1: either bytes or a deserialized python data structure depending on validate_as_json
			:param 2: incoming connection source IP address
			:return: any type of object compatable with to_bytes()
		:param recv_socket: socket to receive data on
		:param ip: IPv4 address to use
		:param validate_as_json: weather to automatically reject data that isn't JSON deserializable
		'''
		s.callback = callback
		s.recv_socket = recv_socket
		s.ip = ip
		s.validate_as_json = validate_as_json

	def start_loop(s, threaded:bool=True) -> None:
		'''
		starts waiting for data on recv_socket
		:param threaded: weather to start a separate thread to run loop
		:return: None
		'''
		s.running = True
		if threaded:
			s.thread = threading.Thread(target=s.loop)
			s.thread.start()
		else:
			s.loop()

	def stop_loop(s) -> None:
		'''
		stops the server
		:return: None
		'''
		s.running = False

	def loop(s) -> None:
		'''
		main loop
		:return: None
		'''
		with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as socket_obj:
			socket_obj.bind(('', s.recv_socket))
			socket_obj.listen()
			while s.running:
				conn, addr = socket_obj.accept()
				with conn:
					data = conn.recv(1024)
					if s.validate_as_json:
						# attempt to decode as ASCII
						try:
							ascii_data = data.decode('ascii')
						except UnicodeDecodeError as e:
							s.send(conn, json.dumps([False, 'client error: could not decode binary as ASCII: ' + str(e)]))
							break
						# attempt to decode as JSON
						try:
							py_obj = json.loads(ascii_data)
						except json.JSONDecodeError as e:
							s.send(conn, json.dumps([False, 'client error: could not decode binary as JSON: ' + str(e)]))
							break
						s.send(conn, s.callback(py_obj, addr))
					else:
						s.send(conn, s.callback(data, addr))

	def send(s, conn, data) -> None:
		'''
		NOTE: this meant to be called internally
		send data
		:param conn: connection object
		:param data: data to send, can be bytes, bytearray, or str
		:return: None
		'''
		# send data
		conn.sendall(to_bytes(data))


class SocketClient:
	def __init__(s, send_socket:int, ip:str='127.0.0.1', chunk_size:int=4096, timeout:int=15):
		'''
		socket client handler
		:param send_socket: socket to send data on
		:param ip: IPv4 address to use
		:param chunk_size: max amount of data to receive at a time
		:param timeout: time to wait for response before timing out
		'''
		s.send_socket = send_socket
		s.ip = ip
		s.chunk_size = chunk_size
		s.timeout = timeout

	def send(s, data) -> bytes:
		'''
		starts a thread that runs send_blocking
		:param data: anything compatible with to_bytes()
		:return: bytes
		'''
		return_mutable = []
		th = threading.Thread(target=lambda: return_mutable.append(s.send_blocking(data)))
		start_t = t()
		th.start()
		while True:
			if t() - start_t >= s.timeout:
				raise TimeoutError(f'timed out after {str(s.timeout)} secs')
			if len(return_mutable) == 1:
				th.join()
				return return_mutable[0]

	def send_blocking(s, data) -> bytes:
		'''
		sends `data` and receives response, this will block until done
		the response format includes a header with the size of the following data for example b"4 abcd" where there is an integer followed by a space, then the data
		:param data: anything compatible with to_bytes()
		:return: bytes
		'''
		socket_obj = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		socket_obj.connect((s.ip, s.send_socket))
		socket_obj.sendall(to_bytes(data))
		res_complete = bytes([])
		first_time = True
		while True:
			res = socket_obj.recv(s.chunk_size)
			if len(res) == 0:
				return res_complete
			if first_time:# get size header
				size_s = res.split(b' ')[0].decode('ascii')
				res = res[len(size_s) + 1:]
				size = int(size_s)
				first_time = False
			res_complete += res
			if len(res_complete) == size:# last of the data
				break
		socket_obj.close()
		return res_complete


class RudderInput:
	'''
	class for managing and giving priority to different rudder control sources
	'''
	def __init__(s, priority:list, rudder=None):
		'''
		NOTE: this class only uses the angle as a relative angle (can be from -90 to 90)
		:param priority: list of input types with the highest priority, from highest to lowest
		:param rudder: boat's rudder object (optional)
		'''
		s.rudder = rudder
		s.priority = priority
		s.inputs = {input_: None for input_ in s.priority}
		s.recalculate_angle()

	def recalculate_angle(s) -> None:
		'''
		NOTE: this does not need to be called externally
		recalculates the rudder angle
		:return: None
		'''
		s.curr_input = None
		s.angle = None
		for input_, value in sorted(s.inputs.items(), key=lambda t: s.priority.index(t[0])):
			if value != None:
				s.curr_input = input_
				s.angle = value
				if s.rudder != None:
					s.rudder.set_angle(value + 270)
				return
		if s.rudder != None:
			s.rudder.set_angle(None)

	def disable_input(s, name:str) -> None:
		'''
		disables an input
		:param name: input name
		:return:
		'''
		assert name in s.priority, f'rudder control input name must be in {str(s.priority)}'
		s.inputs[name] = None
		s.recalculate_angle()

	def set_input(s, name:str, angle:float) -> None:
		'''
		sets the value for input `name`
		:param name: input name
		:param angle: input angle
		:return: None
		'''
		assert name in s.priority, f'rudder control input name must be in {str(s.priority)}'
		angle = max(-90, min(90, angle))
		s.inputs[name] = angle
		s.recalculate_angle()


class Resources:
	'''
	gets the directories and paths for the resources for this installation
	'''
	def __init__(s, app_base_dir:str):
		'''
		check that the resource directory in resources.json is good
		:param app_base_dir: base directory of the app
		'''
		# get resource base dir and make sure it is saved
		os.chdir(app_base_dir)
		try:
			with open('installation.json') as f:
				data = json.loads(f.read())
			s.base_dir = data['resource-directory']
			assert s.check_resource_directory(s.base_dir)
		except Exception:
			s.base_dir = s.get_resource_directory_from_user()
			with open('installation.json', 'w') as f:
				f.write(json.dumps({'resource-directory': s.base_dir}))
		# define the rest of the directories
		s.boat_dir = os.path.join(s.base_dir, 'boat_specs')
		s.maps_dir = os.path.join(s.base_dir, 'maps')
		s.simulations_dir = os.path.join(s.base_dir, 'simulations')
		s.scrots_dir = os.path.join(s.base_dir, 'scrots')

	def get_resource_directory_from_user(s) -> str:
		'''
		uses the command line to get a valid resource directory from user
		:return: str
		'''
		while True:
			dir_ = input('Enter the location of the resource directory to proceed: ')
			if s.check_resource_directory(dir_):
				return dir_
			else:
				print('Not valid')

	def check_resource_directory(s, dir_:str) -> bool:
		'''
		checks that `dir_` is a valid resource directory
		:return: bool
		'''
		# TODO: more comprehensive
		return os.path.isdir(dir_)


class FPSSmoother:
	'''
	keeps a running mean of framerates between updates
	'''
	def __init__(s, n_frames:int=20) -> None:
		'''
		init
		:param frames: number of frames to store
		'''
		# save param
		assert n_frames > 0, 'n_frames must be greater than 0'
		s.n_frames = n_frames
		# default
		s.times = []
		s.prev_t_micros = micros()

	def record(s) -> int:
		'''
		records frame
		:return: time delta in microseconds
		'''
		# record time delta
		curr_t_micros = micros()
		delta_t_micros = curr_t_micros - s.prev_t_micros
		s.prev_t_micros = curr_t_micros
		s.times.append(delta_t_micros)
		# delete oldest record if list is long enough
		if len(s.times) > s.n_frames:
			del s.times[0]
		return delta_t_micros

	def get(s) -> float:
		'''
		calculates mean FPS
		:return: mean FPS
		'''
		return 1_000_000 / (sum(s.times) / s.n_frames)# microseconds


def validate_ipv4(s) -> bool:
	'''
	checks if `s` is a valid IPv4 address
	:param s: string to check
	:return: if it's valid
	'''
	# check type
	if type(s) != str:
		return False
	# check chars
	if False in [c in '.0123456789' for c in s]:
		return False
	# check number of partitions between "."
	nums = s.split('.')
	if len(nums) != 4:
		return False
	# check validity of numbers
	if False in [validate_obj(num, int) for num in nums]:
		return False
	# check ranges
	if False in [0 <= int(num) < 256 for num in nums]:
		return False
	# valid
	return True

def validate_port(s) -> bool:
	'''
	checks if `s` is a valid port
	:param s: string to check
	:return: if it's valid
	'''
	# check as integer
	if not validate_obj(s, int):
		return False
	# check range
	if not 0 <= int(s) < 65536:
		return False
	# pass
	return True

def validate_config_dict(d:dict, default:dict={}, required_keys:list=[], types:dict={}):
	'''
	checks of a config dict is valid
	:param d: dict
	:param default: default keys/values
	:param required_keys: required keys
	:param types: dict of each key and the type that it's value should be
	:return: new dict
	'''
	# check for missing keys
	for key in required_keys:
		if key not in d.keys():
			raise KeyError(f'missing required key "{key}"')
	# check default types
	for key, item in d.items():
		if key not in types.keys():
			continue
		assert validate_obj(item, types[key]), f'key "{key}" must be of type {str(types[key])}'
	# default kays/values
	return {**default, **copy.deepcopy(d)}

def validate_filename(name:str) -> str:
	'''
	validates `name` as a filename
	:param name: filename
	:return: improved version (possibly '')
	'''
	# validate name
	name = name.replace('/', '_').replace('\\', '_').replace(' ', '_').replace('\t', '_').replace(':', '-')
	return name

def HTTP_GET_validate(req:str) -> tuple:
	'''
	validates an HTTP GET request
	:param req: request string
	:return: tuple:
		* Whether directory could be extracted
		* GET directory
	'''
	try:
		line = req.split('\n')[0]
		dir_ = line.split(' ')[1]
	except Exception:
		return False, ''
	return True, dir_

def open_docs() -> None:
	'''
	opens the documentation HTML file
	:return: None
	'''
	webbrowser.open('file://' + base_dir + '/docs/documentation.html')

def to_bytes(data) -> bytes:
	'''
	turns `data` into bytes
	:param data: bytes, bytearray, str, or None
	:return: bytes
	'''
	assert type(data) in [str, bytearray, bytes, type(None)], 'first arg must be of type bytes, bytearray, str, or None'
	if type(data) == str:
		bin_data = bytes(data, 'utf-8')
	if type(data) == bytearray:
		bin_data = bytes(data)
	if type(data) == bytes:
		bin_data = data
	if data == None:
		bin_data = bytes(bytearray([]))
	return bin_data

def recursive_index(obj, lst:list):
	'''
	recursive index function (with __getitem__)
	:param obj: object to recursively index
	:param lst: list of layers of obj
	:return: anything
	'''
	if len(lst) == 0:
		return obj
	else:
		return recursive_index(obj[lst[0]], lst[1:])

def compress_coords(l:list, tolerance:float=0):
	'''
	removes uneccesary points from a series of coordinates `l`
	:param l: list of coordinate points
	:param tolerance: max difference of angle between vertices from 180 to delete
	:return: new list
	'''
	if len(l) <= 2:
		return l# nothing to be done
	curr_lst = l[:3]
	new_lst = []
	for i, c in enumerate(l):
		if i not in [0, len(l) - 1] and abs((Vec2d(*l[i - 1]) - Vec2d(*c)).angle_degrees - (Vec2d(*c) - Vec2d(*l[i + 1])).angle_degrees) <= tolerance:
			continue
		new_lst.append(c)
	return new_lst

def convert_pos(pos, type_):
	'''
	converts pos to type_
	:param pos: can be of type list, tuple, pymunk.vec2d.Vec2d, or shapely.geometry.Point
	:param type_: one of the above
	:return: one of the above
	'''
	# assertions
	assert type(pos) in [list, tuple, Vec2d, Point]
	if type(pos) == type_:
		return pos
	# convert to list
	if type(pos) in [list, tuple, Vec2d]:
		l = list(pos)
	if type(pos) == Point:
		l = list(pos.coords)
	# assertions
	assert len(l) == 2, 'there must be 2 coordinates'
	for item in l:
		if type(item) not in [int, float]:
			raise TypeError(f'coordinates must be of type int or float, not {str(type(item))}')
	# convert to type
	if type_ == tuple:
		return tuple(l)
	if type_ == Vec2d:
		return Vec2d(*l)
	if type_ == Point:
		return Point(l)
	return l

def update_json_file(path:str, d:dict={}, write_if_invalid:bool=False) -> list:
	'''
	updates keys/values in JSON file
	:param path: path to file
	:param d: dict to update from
	:param write_if_invalid: whether to write `d` by itself to the file if the original can't be found or decoded
	:return: [(bool): whether there have been no problems, error message or None]
	'''
	rtrn = [True, None]
	valid = True
	try:
		with open(path) as f:
			try:
				config = json.loads(f.read())
			except json.JSONDecodeError as e:
				config = {}
				valid = False
				rtrn = [False, f'could not decode {path} as a JSON file: {str(e)}']
	except FileNotFoundError as e:
		config = {}
		valid = False
		rtrn = [False, f'could not find file: {str(e)}']
	if write_if_invalid or valid:
		with open(path, 'w') as f:
			f.write(json.dumps({**config, **d}))
	return rtrn

def load_settings(type_:str, sim:str=None) -> dict:
	'''
	loads settings from settings.json, current simulation file, or s.settings_d.
	loads settings.json and overwrites any keys that are also in the "settings" dict in the current simulation file `sim`
	:param type_: type of settings to load, can be "simulator" or "GUI"
	:param sim: simulation name to get local settings for
	:return: settings dict
	'''
	assert type_ in ['simulator', 'GUI']
	# get global settings
	os.chdir(resources.base_dir)
	with open('settings.json') as f:
		try:
			global_d = json.loads(f.read())
		except json.JSONDecodeError as e:
			raise ValueError(f'could not decode settings.json: {str(e)}')
	d = global_d[type_]
	# get local settings (only if for a simulation)
	if type_ == 'simulator' and (sim is not None):
		os.chdir(resources.simulations_dir)
		with open(sim + '.json') as f:
			try:
				sim_d = json.loads(f.read())
			except json.JSONDecodeError as e:
				raise ValueError(f'could not decode simulation file {sim}.json: {str(e)}')
		# local settings override global settings
		if 'settings' in sim_d.keys():
			d = {**d, **sim_d}
	# check all keys exist
	required_key_types = {
		'GUI': {
			'floodfill-land': bool,
			'show-true-wind': bool,
			'show-timer': bool,
			'reverse-scrolling': bool,
			'show-tracer': bool,
			'show-vectors': bool,
			'show-end-flag': bool,
			'show-performance': bool,
			'show-boat-labels': bool,
			'control-panel-side': str,
			'colors': dict,
			'pixel-units': dict
		},
		'simulator': {
			'save-sims': bool,
			'lag-limit': float,
			'max-rudder-movement': float,
			'client-timeout': float,
			'sanity-limits': dict,
		}
	}
	# validate settings dictionary
	validate_config_dict(d, required_keys=required_key_types[type_].keys(), types=required_key_types[type_])
	# check for more detailed errors
	if type_ == 'GUI':
		# control panel side
		d['control-panel-side'] = d['control-panel-side'].upper()
		assert d['control-panel-side'] in ['L', 'R'], 'the value for "control-panel-side" must be either "L" or "R".'
		# pixel units
		tmp_d = d['pixel-units']
		if type(tmp_d) != dict:
			raise TypeError('pixel units value must be dictionary')
		for key, value in tmp_d.items():
			if type(key) != str:
				raise TypeError('pixel units keys must be string')
			if not (type(value) in [int, float]):
				raise TypeError('pixel units value must be of type int or float')
		for req_key in ['force', 'distance', 'momentum']:
			if req_key not in tmp_d.keys():
				raise KeyError(f'missing key in pixel units: {req_key}')
		# colors
		required_colors = ['true-wind', 'app-wind', 'drag-force', 'velocity', 'rudder-force', 'sail-force', 'total-sail-force', 'ocean', 'land', 'text-fg', 'text-bg', 'tracer-path']
		colors = d['colors']
		validate_config_dict(colors, required_keys=required_colors, types={key: list for key in required_colors})
		for c in required_colors:
			if len(colors[c]) != 3:
				raise KeyError(f'all values in the "colors" dict in settings.json must be lists of length 3')
		d['colors'] = {key: tuple(color) for key, color in colors.items()}
	return d

def paste_text(img, pos:tuple, str_:str, font:image_font.truetype, fg:tuple=(0, 0, 0), bg:tuple=(255, 255, 255)) -> None:
	'''
	pastes text `str_` on image at `pos` with background box
	:param img: img to paste on
	:param pos: position of top-left corner of text (PIL-style coordinates)
	:param str_: text string to paste, can be multiline
	:param font: PIL truetype font object
	:param fg: foreground color, RGB tuple
	:param bg: background color, RGB tuple
	:return: None (modifies the image in-place)
	'''
	drawer = image_draw.Draw(img)
	# actualy the best way to create a background, see stckoverflow question #18869365
	drawer.rectangle(tuple(list(pos)+[get_font_size(font, str_)[i]+pos[i] for i in range(2)]), fill=bg)
	drawer.text(pos, str_, fill=fg, font=font)

def paste_vector_on_img(img:image.Image, start, v, pixels_per_unit_start:int=1, pixels_per_unit_vec:int=1, color:tuple=(0, 0, 0), width:int=2, origin=Vec2d(0, 0), draw_arrow:bool=True, min_len:int=1, reverse_y_start:bool=True) -> None:
	'''
	NOTE: both vectors will be converted to PIL-style coordinates (Y reversed)
	NOTE: all vectors used (start, v, and origin) can be any type accepted as the first arg by convert_pos()
	pastes a vector on image `img`
	:param img: image to paste vector on
	:param start: where to place the start of the vector
	:param v: vector to be drawn
	:param pixels_per_unit_start: pixels per unit of the start position vector
	:param pixels_per_unit_vec: pixels per unit of the vector
	:param color: color to make arrow (len=3)
	:param width: width of line in pixels
	:param origin: offset for both vectors
	:param draw_arrow: weather to draw the arrow head
	:param min_len: minumum lengh of the vector in pixels, if the vector (in pixels) is shorter, it isn't displayed
	:param reverse_y_start: whether to reverse the direction of the Y-axis for the starting vector
	:return: None (modifies the image in-place)
	'''
	# convert to Vec2d
	start = convert_pos(start, Vec2d)
	v = convert_pos(v, Vec2d)
	origin = convert_pos(origin, Vec2d)
	# create drawer object
	drawer = image_draw.Draw(img)
	# multiply by pixels per unit to get values in pixels
	start *= pixels_per_unit_start
	v *= pixels_per_unit_vec
	# reverse Y of start
	if not reverse_y_start:
		start = Vec2d(start.x, img.size[1] - start.y)
	# return if to short
	if v.length < min_len:
		return
	# create absolute end point
	end = v + start
	# apply origin
	start += origin
	end += origin
	# reverse Y
	start = Vec2d(start.x, img.size[1] - start.y)
	end = Vec2d(end.x, img.size[1] - end.y)
	# draw line
	drawer.line([(int(start.x), int(start.y)), (int(end.x), int(end.y))], color, width)
	# draw arrow head
	if draw_arrow:
		arrow_tips = [end + (_v.rotated(-v.angle)) for _v in [Vec2d(-5, -4), Vec2d(-5, 4)]]
		[drawer.line([(int(end.x), int(end.y)), (int(_v.x), int(_v.y))], color, width) for _v in arrow_tips]

def dot_on_img(img:image.Image, pos:list, diameter:int, fill:tuple) -> None:
	'''
	draws a dot on `img`
	:param img: image to draw dot on
	:param pos: position on image
	:param diameter: diameter of the dot
	:param fill: fill color
	:return: None (modifies the image in-place)
	'''
	pos = [int(c) for c in pos]
	radius = int(diameter / 2)
	for x in range(pos[0] - radius, pos[0] + radius):
		for y in range(pos[1] - radius, pos[1] + radius):
			if Vec2d(x - pos[0], y - pos[1]).length <= radius:
				try:
					img.putpixel((x, y), fill)
				except IndexError:
					pass

def get_font_size(font, string):
	font_bb = font.getbbox(string)
	return (font_bb[2] - font_bb[0], font_bb[3] - font_bb[1] + 2)

def torque_on_body(start:Vec2d, force:Vec2d) -> float:
	'''
	based off of https://courses.lumenlearning.com/suny-osuniversityphysics/chapter/10-6-torque
	calculates the torque on a rigid body with the coordinate origin as the turning point
	:param start: place whare the force is applied
	:param force: force on body
	:return: torque: anticlockwise = +, clockwise = -
	'''
	return -start.length * force.length * math.sin((force.angle_degrees - (start.angle_degrees + 180)) * TC)

def sideways_drag_force_on_flat_object(density:float, speed:Vec2d, area:float, angle:float) -> Vec2d:
	'''
	meant to be used for stuff like sail and rudder force, the returned force angle will be perpindicular to `angle`
	:param density: density of fluid, pounds/foot^3
	:param speed: speed vector of the object in the fluid in ft/sec
	:param area: area of the object from the side, ft^2
	:param angle: angle of the object, degrees anticlockwise from east
	:return: drag force vector
	'''
	# I think this is right
	angle %= 180
	# convert to speed according to the object
	apparent_speed = speed.rotated_degrees(-(angle - 90) % 360)# water speed relative to the object
	# sideways force according to the object
	# flat object drag Cd from https://www.grc.nasa.gov/www/k-12/airplane/shaped.html
	sideways_force = drag(apparent_speed.x, 1.28, density, area)
	# object force in normal coordinates
	force = Vec2d(sideways_force, 0).rotated_degrees((angle - 90) % 360)
	return force

def force_torque_coe(forces:list, centers_of_effort:list) -> list:
	'''
	confirm that this works,
	calculates the linear force and torque of a list of force vectors and force position vectors
	:param forces: list of Vec2d objects for each force
	:param centers_of_effort: list of Vec2d objects for position of each vector in `forces`
	:return: [total force:Vec2d, total torque:float, total center of effort:Vec2d]
	'''
	assert len(forces) == len(centers_of_effort)
	torque = 0
	total_force = Vec2d(0, 0)
	centers_of_effort_rep_values = []
	for force, center_of_effort in zip(forces, centers_of_effort):
		torque += torque_on_body(center_of_effort, force)
		total_force += force
		centers_of_effort_rep_values.append(center_of_effort * force.length)
	total_center_of_effort_sums = []
	for i in range(2):
		try:
			total_center_of_effort_sums.append(sum([[v.x, v.y][i] for v in centers_of_effort_rep_values]) / total_force.length)
		except ZeroDivisionError:
			total_center_of_effort_sums.append(0)
	return [total_force, torque, Vec2d(*total_center_of_effort_sums)]

def drag(speed:float, drag_c:float, density:float, scale:float) -> float:
	'''
	calculates drag force
	:param speed: speed
	:param drag_c: drag coefficient
	:param density: density of fluid
	:param scale: depends on boat size
	:return: drag force
	'''
	force = drag_c * density * (speed**2) * scale * 0.5
	if speed < 0:# to fix speed^2 absolute value problem
		return -force
	return force

def angular_drag(speed:float, drag_c:float, density:float, scale:float) -> float:
	'''
	calculates angular drag force, written from https://physics.stackexchange.com/questions/304742/angular-drag-on-body
	:param speed: speed (deg/sec)
	:param drag_c: drag coeffecient
	:param density: density of fluid
	:param scale: depends on boat size
	:return: drag torque
	'''
	force = drag_c * density * (speed**2) * scale * -0.5
	if speed < 0:# to fix speed^2 problem
		return -force
	return force

def t() -> float:
	'''
	gets the current timestamp with microsecond resolution
	:return: timestamp
	'''
	return micros() / 1_000_000

def validate_obj(obj, type_:type) -> bool:
	'''
	validates an object `obj` as an type(type_)
	:param obj: object to validate
	:param type_: type to validate `obj` as
	:return: whether `obj` can be represented as type `type_`
	'''
	try:
		type_(obj)
	except Exception:
		return False
	return True

def diff_between_angles(a:float, b:float) -> float:
	'''
	calculates difference between 2 angles
	:param a: first angle
	:param b: second angle
	:return: angle difference
	'''
	return (((b - a) + 180) % 360) - 180

def is_angle_between(x:float, a:float, b:float, include_edgcase:bool=False) -> bool:
	'''
	NOTE: the order of angles A and B matters
	determines whether angle `x` is between angle `a` and angle `b`
	:param x: angle to be tested
	:param a: clockwise limit angle
	:param b: anticlockwise limit angle
	:param include_edgcase: whether to return true if x is right on a or b
	:return: result
	'''
	if include_edgcase:
		return 0 <= (x - a) % 360 <= (b - a) % 360
	else:
		return 0 < (x - a) % 360 < (b - a) % 360

def sign(val) -> int:
	'''
	converts `val` to a sign
	:param val: either a number or boolean
	:return: int (-1 or 1)
	'''
	if type(val) == bool:
		return (int(val) * 2) - 1
	else:
		return [-1, 1][int(val >= 0)]

def dbp(s) -> None:
	'''
	debug print
	:param s: string to print
	:return: None
	'''
	if DEBUG:
		print(f'debug print: {s}')


DEBUG = False
DEFAULT_PORT = 30300# see https://en.wikipedia.org/wiki/List_of_TCP_and_UDP_port_numbers#cite_note-IANA-2
base_dir = os.getcwd()
imgs_dir = os.path.join(base_dir, 'imgs')
http_dir = os.path.join(base_dir, 'http')
resources = Resources(app_base_dir=base_dir)
version_tuple = tuple(base_dir.split("_")[-2][1:].split('.'))
__version__ = f'{base_dir.split("_")[-2][1:]} ({base_dir.split("_")[-1].title()})'
TC = math.pi/180# degrees * TC = radians
