#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  sailboat_simulator.py
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
import threading

program_name = 'Sailboat Simulator'
author = 'Hadrian Ward'

# check version
import sys
py_ver = list(sys.version_info)
if py_ver[0] < 3:
	print('this program requires a minimum python version of 3, you are running python ' + '.'.join([str(n) for n in py_ver[:3]]))
	sys.exit(1)

# imports
# built-ins
import os, json, time, copy, traceback, random, math
import multiprocessing as mp
import datetime as dt

# third-party, from PyPi
import tkinter as tk
from pymunk.vec2d import Vec2d# very useful
from send2trash import send2trash
from PIL import Image as image
from PIL import ImageTk as image_tk

# from CWD
import GUIs, extras, graphics, simulator

# classes
class AutopilotGUI:
	'''
	handles the GUI for the autopilot
	'''
	def __init__(s, frame:tk.Frame, users:list, end_pos:Vec2d, config:dict):
		'''
		init
		:param frame: tkinter frame to use for the GUI
		:param users: list of all usernames on the server
		:param end_pos: end position to use for global pos default
		:param config: config data
		'''
		# save args
		s.frame = frame
		# flags and defaults
		s.enable = tk.BooleanVar()
		s.status_label_str = tk.StringVar()
		s.new_course_selection_mode = tk.StringVar()
		s.new_course_selection_mode.set('pos')
		# save config
		default_config = {'target-pos': ['global-pos', [0, 0]], 'enabled': False}
		s.server_updates = {**default_config, **config}
		s.enable.set(s.server_updates['enabled'])
		# default status text
		s.default_status_text = 'Autopilot: {}\nestimated travel time: {}'
		s.status_label_str.set(s.default_status_text.format('disabled', '--:--'))
		# setup GUI
		curr_row = 0
		# row 0: enable checkbutton
		tk.Checkbutton(s.frame, variable=s.enable, command=lambda: s.set_enabled(s.enable.get()), text='Enable Autopilot').grid(row=curr_row, column=0)
		# row 1: status label
		curr_row += 1
		tk.Label(s.frame, textvariable=s.status_label_str).grid(row=curr_row, column=0)
		# rows 2 and 3: set new course option radiobutton
		for text, value in zip(['Global position', 'Relative to boat', 'Track user'], ['pos', 'angle', 'user']):
			curr_row += 1
			tk.Radiobutton(s.frame, text=text, variable=s.new_course_selection_mode, value=value, command=s.set_new_course_input).grid(row=curr_row, column=0)
		# row 4: set new course option frame
		curr_row += 1
		s.new_course_frame = tk.Frame(s.frame)
		s.new_course_frame.grid(row=curr_row, column=0)
		s.new_course_GUI = GUIs.AutopilotTargetInput(s.new_course_frame, s.set_entries_valid, users, end_pos)
		# row 5: new course button
		curr_row += 1
		s.new_course_button = tk.Button(s.frame, text='Set new course', command=s.new_course, state='disabled')
		s.new_course_button.grid(row=curr_row, column=0)
		# set default course input type
		s.new_course_selection_mode.set('pos')
		s.set_new_course_input()

	def update(s, update_config:dict) -> None:
		'''
		updates the autopilot
		:param update_config: data from "autopilot" in the server return data, see ProcManager.recv_client_data() in simulator.py
		:return: None
		'''
		if not s.enable.get():
			s.status_label_str.set(s.default_status_text.format('disabled', '--:--'))
			return
		# update status message
		status = ['setting course', 'on course'][int(update_config['on-course'])] + (', tacking' * int(update_config['tacking']))
		if update_config['travel-time'] == None:
			travel_time_str = '--:--'
		else:
			travel_time_str = f'~{str(dt.timedelta(seconds=max(int(update_config["travel-time"]), 0)))}'
		s.status_label_str.set(s.default_status_text.format(status, travel_time_str))

	def set_new_course_input(s) -> None:
		'''
		called when the radiobutton is changed to select the new course input type
		:return: None
		'''
		mode = s.new_course_selection_mode.get()
		s.new_course_GUI.set_input_type(mode)

	def new_course(s) -> None:
		'''
		called when the "set new course" button is clicked
		:return: None
		'''
		s.server_updates['target-pos'] = s.new_course_GUI.get()

	def set_enabled(s, state:bool) -> None:
		'''
		puts a request to the server to enable/disable the autopilot
		:param state: enable state
		:return: None
		'''
		s.server_updates['enabled'] = state

	def set_entries_valid(s, valid:bool) -> None:
		'''
		called by any keyrelease event on an entry widget
		:param valid: whether the input GUI is valid
		:return: None
		'''
		s.new_course_button.config(state=['disabled', 'normal'][int(valid)])

	def get_server_updates(s) -> dict:
		'''
		gets the server updates
		:return: server update dictionary
		'''
		rtrn = s.server_updates
		s.server_updates = copy.copy({})
		return rtrn

	def save(s) -> dict:
		'''
		creates a dict to save to a simulation file
		:return: JSON serializable dict
		'''
		return {'target-pos': list(s.pos), 'enabled': s.enable.get()}


class SimClient:
	'''
	simulator client class, this handles the user I/O and GUI
	'''
	def __init__(s,
		frame:tk.Frame,
		window_size:tuple,
		process_controller:bool,
		public:bool,
		port:int=None,
		ip:str='127.0.0.1',
		sim_name:str=None,
		username:str='__admin__',
		password:str=None,
		sim_password:str=None):
		'''
		:param frame: tk frame to use
		:param window_size: size of the GUI window
		:param process_controller: whether this client will be the controller of the sim server process
		:param public: whether the server will be public
		:param port: server port (only used if not an admin)
		:param ip: server IPv4 address (only used if not an admin)
		:param sim_name: simulation name (only used if admin == True)
		:param username: username
		:param password: password
		:param sim_password: simulation server password
		'''
		# assertions
		assert public or process_controller
		# save params
		s.frame = frame
		s.window_size = window_size
		s.process_controller = process_controller
		s.public = public
		s.port = port
		s.ip = ip
		s.sim_name = sim_name
		s.username = username
		s.password = password
		s.sim_password = sim_password
		# set flags and records
		s.admin = s.username == '__admin__'
		s.errors = []
		s.prev_t_micros = extras.micros()
		s.frame_time = 0
		s.paused = tk.BooleanVar()
		s.finished = False
		s.fps_tracker = extras.FPSSmoother()
		s.server_fps = 0
		s.waiting_on_server = False
		s.sim_time = 0
		s.quit = False# flag for the main GUI
		s.mouse_img_pos = None
		s.alert = extras.Alert()
		s.img_mouse_pos = None
		s.minimap_mouse_pos = None# possible course for autopilot
		s.time_logger = extras.TimeLogger()
		s.time_logger.clear()
		s.time_logger_results = ''
		s.callback_errors = []# errors from tkinter callback functions
		s.mouse_in_rudder_ctrl_box = False
		s.user_input = {'boat': {}, 'autopilot': {}}
		if s.admin:
			s.admin_commands = []
		s.min_img_size = (200, 200)# minimum image size
		# settings
		s.load_settings()
		# process controller stuff
		if s.process_controller:
			# default port
			if s.port is None:
				s.port = extras.DEFAULT_PORT
				if s.public:
					s.alert.add(f'WARNING: this server defaulted to port {str(port)}', (255, 0, 0), 5, True)
			# assertions
			assert type(s.sim_name) == str
			# flags and defaults
			s.admin_code = random.randint(0, 2**32)
			s.username = '__admin__'
			s.password = str(s.admin_code)
			# init server
			s.server_recv_queue = mp.Queue()
			s.sim_server = simulator.ProcManager(s.server_recv_queue, s.admin_code, s.sim_name, s.port, s.public)
			s.ip = s.sim_server.ip
			# start server
			os.chdir(extras.base_dir)# so that server process gets the resource dirs correct
			s.sim_server_proc = mp.Process(target=s.sim_server.main_loop, name='sailboat-simulator-server')
			s.sim_server_proc.daemon = True
			extras.dbp('SimClient.__init__: starting server process')
			s.sim_server_proc.start()
			# wait for the server to start listening
			start_t = time.time()
			while s.server_recv_queue.empty():
				if time.time() - start_t >= simulator.SERVER_INIT_TIMEOUT:
					raise TimeoutError('timed out waiting for server process to become responsive')
		# init socket client
		s.socket_client = extras.SocketClient(s.port, s.ip)
		# create authentication
		s.auth = s.create_auth()
		# get start data from server and check for errors
		extras.dbp('SimClient.__init__: getting server start config')
		server_start_config = simulator.ProcManager.check_server_response(s.socket_client.send(json.dumps(['JOIN', {'auth': s.auth}])))
		s.prev_t_server = extras.micros()
		# create admin controls
		if s.admin:
			s.admin_control_window = GUIs.AdminControlWindow(
				master_frame=s.frame,
				command_callback=s.admin_command,
				global_reset_callback=lambda: s.reset(global_=True),
				usernames=server_start_config['clients'].keys(),
				boats_static_config=server_start_config['boats-static-config'],
				settings=s.settings,
				user_boat_types={name: config['boat']['type'] for name, config in server_start_config['clients'].items()},
				map_data=copy.deepcopy(server_start_config['map'])
			)
		# setup GUI
		s.create_gui()
		self_client_config = server_start_config['clients'][s.username]
		# set default image size
		img_render_size = s.set_img_size(tuple(map(lambda x: x - 100, s.window_size)))
		# incompatibility warning
		server_ver = tuple(server_start_config['server-software-version'])
		if server_ver != extras.version_tuple:
			s.alert.add(f'INCOMPATIBILITY WARNING: the server is running version {".".join(server_ver)}, this is version {".".join(extras.version_tuple)}', (255, 0, 0), 10)
		# init objects
		s.rudder_control = extras.RudderInput(['user/keyboard', 'user/mouse', 'user/slider'])
		extras.dbp('SimClient.__init__: initiating renderer')
		s.renderer = graphics.Renderer(
			s.img_label,
			s.graphics_settings_frame,
			server_start_config['map'],
			server_start_config['clients'],
			s.settings,
			s.alert,
			s.time_logger,
			s.common_pixel_units,
			img_render_size,
			s.username,
			s.set_sheeting_angle,
			s.rudder_control
		)
		s.autopilot = AutopilotGUI(frame=s.autopilot_frame, users=[username for username, _ in server_start_config['clients'].items()], end_pos=s.renderer.map.end, config=self_client_config['autopilot'])
		# scale pixel units
		s.common_pixel_units.scale(min(s.renderer.size) / (s.renderer.main_boat.perim_max_radius * s.common_pixel_units.get('distance') * 4))
		# setup start data
		s.setup_state_data(server_start_config)
		# finish message
		s.finish_message = 'You have reached Your destination'
		# lag message
		s.lag_message = 'lag limit reached'

	def create_auth(s) -> list:
		'''
		:return: authentication list
		'''
		return [s.username, s.password, s.sim_password]

	def load_settings(s) -> None:
		'''
		loads settings from settings.json
		:return: None
		'''
		# load settings
		d = extras.load_settings('GUI')
		s.settings = d
		s.reverse_scrolling = d['reverse-scrolling']
		s.control_panel_side = d['control-panel-side']
		# update pixel units
		try:
			s.common_pixel_units.update(d['pixel-units'])
		except AttributeError:
			s.common_pixel_units = graphics.CommonPixelUnits(d['pixel-units'])
		# try to update renderer
		try:
			s.renderer.update_settings(d)
		except AttributeError:# renderer hasn't been created yet, ignore
			pass
		# make simulator reload settings
		try:
			s.admin_command(['RELOAD-SETTINGS'])
		except AttributeError:
			pass
		if s.admin:
			# load admin control window
			try:
				s.admin_control_window.load_settings(d)
			except Exception:
				pass

	def create_gui(s) -> None:
		'''
		creates the gui
		:return: None
		'''
		extras.dbp('SimClient.__init__: setting up the GUI')
		# get control pane side
		image_col, side_frame_col = [(0, 1), (1, 0)][int(s.control_panel_side == 'L')]
		# image
		s.curr_tk_img = image_tk.PhotoImage(image.new('RGB', (10, 10), (255, 255, 255)))
		s.img_label = tk.Label(s.frame, image=s.curr_tk_img)
		s.img_label.grid(row=0, column=image_col, sticky='nsew')
		s.img_label.bind('<Button-1>', s.img_clicked)
		if s.admin:
			s.img_label.bind('<Button-3>', lambda _: s.toggle_paused_state(global_=True))
		s.img_label.bind('<Leave>', s.mouse_exit_img)
		s.img_label.bind('<Motion>', s.mouse_move_on_img)
		s.img_label.bind('<MouseWheel>', s.scroll_on_img)
		s.img_label.bind('<KeyPress>', lambda e: s.key_event_img(e, True))
		s.img_label.bind('<KeyRelease>', lambda e: s.key_event_img(e, False))
		s.frame.grid_rowconfigure(0, weight=1)
		s.frame.grid_columnconfigure(image_col, weight=1)
		# side frame
		s.side_frame = tk.Frame(s.frame)
		s.side_frame.grid(row=0, column=side_frame_col)
		# side_frame row 0: graphics settings frame
		s.graphics_settings_frame = tk.Frame(s.side_frame)
		s.graphics_settings_frame.grid(row=0, column=0)
		# side_frame row 1: inputs frame
		s.inputs_frame = tk.Frame(s.side_frame)
		s.inputs_frame.grid(row=1, column=0)
		curr_row = 0
		# input 0: pause checkbutton
		curr_row += 1
		tk.Checkbutton(s.inputs_frame, text='Pause', variable=s.paused, command=lambda: s.toggle_paused_state(from_checkbutton=True)).grid(row=curr_row, column=0)
		# input 1: time constant slider
		if s.admin:
			curr_row += 1
			tk.Label(s.inputs_frame, text='Time ratio (log)').grid(row=curr_row, column=0)
			s.time_const_slider = tk.Scale(s.inputs_frame, from_=-2, to=2, command=lambda val: s.admin_command(['SET-TIME-CONST', 10**float(val)]), resolution=0.1, orient=tk.HORIZONTAL, tickinterval=4)
			s.time_const_slider.grid(row=curr_row, column=1)
			s.time_const_slider.bind('<Button-1>', lambda _: s.time_const_slider.focus_set())
		# rudder angle
		curr_row += 1
		tk.Label(s.inputs_frame, text='Rudder angle').grid(row=curr_row, column=0)
		s.rudder_angle_scale = tk.Scale(s.inputs_frame, from_=-90, to=90, command=lambda value_str: s.rudder_control.set_input('user/slider', float(value_str)), orient=tk.HORIZONTAL, resolution=0.1, tickinterval=90)
		s.rudder_angle_scale.grid(row=curr_row, column=1)
		s.rudder_angle_scale.bind('<Button-1>', lambda _: s.rudder_control.set_input('user/slider', float(s.rudder_angle_scale.get())))
		s.rudder_angle_scale.bind('<ButtonRelease-1>', lambda _: s.rudder_control.disable_input('user/slider'))
		# autopilot frame
		curr_row += 1
		s.autopilot_frame = tk.Frame(s.inputs_frame)
		s.autopilot_frame.grid(row=curr_row, column=0, columnspan=2)
		# reset
		curr_row += 1
		s.reset_bttn = tk.Button(s.inputs_frame, text='Reset', command=s.reset)
		s.reset_bttn.grid(row=curr_row, column=0, columnspan=2)
		# save screenshot button
		curr_row += 1
		tk.Button(s.inputs_frame, text='Save screenshot', command=s.save_scrot).grid(row=curr_row, column=0, columnspan=2)
		# reload settings button
		curr_row += 1
		tk.Button(s.inputs_frame, text='Reload settings', command=s.load_settings).grid(row=curr_row, column=0, columnspan=2)
		# open docs button
		curr_row += 1
		tk.Button(s.inputs_frame, text='Open documentation', command=extras.open_docs).grid(row=curr_row, column=0, columnspan=2)
		if s.admin:
			# admin control window
			curr_row += 1
			tk.Button(s.inputs_frame, text='Admin controls', command=s.admin_control_window.open_).grid(row=curr_row, column=0, columnspan=2)
		# leave server button
		if not s.process_controller:
			curr_row += 1
			tk.Button(s.inputs_frame, text='Leave server', command=s.leave_server).grid(row=curr_row, column=0, columnspan=2)
		# connection status label
		curr_row += 1
		s.connection_status_label = tk.Label(s.inputs_frame, text='')
		s.connection_status_label.grid(row=curr_row, column=0, columnspan=2)

	def setup_state_data(s, server_start_config:dict) -> None:
		'''
		used in __init__ and after a reset to load the GUI and various other objects with start data from the server
		:param server_start_config: see simulator.Simulator.serializable('client')
		:return: None
		'''
		self_client_config = server_start_config['clients'][s.username]
		# flags
		s.paused.set(self_client_config['paused'])
		s.boat_enabled = self_client_config['enabled']
		s.globally_paused = server_start_config['paused']
		# GUI
		s.rudder_angle_scale.set(self_client_config['boat']['rudder-angle'] - 270)
		s.rudder_control.disable_input('user/slider')
		s.autopilot.enable.set(self_client_config['autopilot']['enabled'])
		if s.admin:
			s.time_const_slider.set(math.log(server_start_config['timer']['ratio'], 10))
		s.set_controls_state(self_client_config['enabled'])
		# renderer
		s.renderer.setup_state_data(self_client_config)

	def admin_command(s, lst:list) -> None:
		'''
		puts an admin command in s.user_input only if s.admin
		:param lst: admin command list
		:return: None
		'''
		if s.admin:
			s.admin_commands.append(lst)

	def update(s) -> None:
		'''
		client update
		:return: None
		'''
		# timing stuff
		try:
			s.time_logger.stop_log('tkinter loop')
		except Exception:# if it's the first iteration this won't work
			pass
		s.fps_tracker.record()
		s.fps = s.fps_tracker.get()
		s.frame_time = (extras.micros() - s.prev_t_micros) / 1_000_000
		s.prev_t_micros = extras.micros()
		# connection status
		server_t = (extras.micros() - s.prev_t_server) / 1_000_000
		if server_t < 1:
			s.connection_status_label.config(text='Connected to server', fg='green')
		else:
			s.connection_status_label.config(text=f'Last connected {str(int(round(server_t)))} seconds ago', fg='red')
		# check server request thread
		if not s.waiting_on_server:# either first time or server response has been received
			# quit thread
			try:
				s.server_request_thread.join()
			except AttributeError:
				pass
			else:
				main_boat_update = s.server_response['clients'][s.username]
				# admin control window
				if s.admin and s.admin_control_window.enabled:
					if 'client-states' in s.server_response['global-data'].keys() and not (s.admin_control_window.user_selected is None):
						s.admin_control_window.setup_state_data(
							curr_user_config=copy.deepcopy(s.server_response['clients'][s.admin_control_window.user_selected]['boat']),
							users_admin_view_status=s.server_response['global-data']['client-states'],
							global_wind=Vec2d(*s.server_response['global-data']['wind'])
						)
				# alerts
				[s.alert.add(*lst) for lst in main_boat_update['general']['alerts']]
				# boat stuff
				if s.boat_enabled:
					# update autopilot
					s.autopilot.update(main_boat_update['autopilot'])
				# update renderer
				img_rudder_ctrl_status = {(0, 0): 0, (1, 0): 2, (1, 1): 2, (0, 1): 1}[(s.mouse_in_rudder_ctrl_box, s.img_mouse_pos != None)]
				s.renderer.update(s.server_response, s.autopilot.enable.get(), s.time_logger_results, s.fps, img_rudder_ctrl_status)
			# restart it
			s.server_request_thread = threading.Thread(target=s.server_update_async)
			s.server_request_thread.start()
		# check window size
		s.set_img_size((s.frame.winfo_width(), s.frame.winfo_height()))
		# update image
		s.time_logger.start_log('graphics')
		s.renderer.render_img()
		s.time_logger.stop_log('graphics')
		# update time logger
		s.time_logger_results = str(s.time_logger)
		s.time_logger.clear()
		s.time_logger.start_log('tkinter loop')

	def server_update_async(s) -> None:
		'''
		blocks until timeout or server responds
		updates everything that depends on data from the server
		:return: None
		'''
		# step 1: prepare to send user input to server -----------------------------------------------------------------
		s.waiting_on_server = True
		if s.rudder_control.angle != None:
			s.user_input['boat']['rudder'] = s.rudder_control.angle
		s.user_input['autopilot'] = s.autopilot.get_server_updates()
		update_dict = {'auth': s.auth, 'user-input': s.user_input, 'render-dist': (Vec2d(*s.renderer.size).length * 0.5) / s.common_pixel_units.get('distance')}
		# admin stuff
		if s.admin:
			# quit flag
			if True in ['QUIT' in lst for lst in s.admin_commands]:
				s.quit = True# server will quit after this update
			# extra boat for admin control window
			if not (s.admin_control_window.user_selected is None):
				update_dict['render-dist-extra-boats'] = [s.admin_control_window.user_selected]
				s.admin_command(['STATUS'])
			update_dict['admin-commands'] = s.admin_commands
			s.admin_commands = []
		# step 2: send request to server and wait for response ---------------------------------------------------------
		server_response_bytes = s.socket_client.send(json.dumps(['UPDATE', update_dict]))
		s.prev_t_server = extras.micros()
		# step 3: check if update was successful -----------------------------------------------------------------------
		s.user_input['boat'] = copy.copy({})
		s.user_input['autopilot'] = copy.copy({})
		s.user_input['reset'] = False
		if 'paused' in s.user_input.keys():
			del s.user_input['paused']
		s.server_response = simulator.ProcManager.check_server_response(server_response_bytes)
		main_boat_update = s.server_response['clients'][s.username]
		# step 4: check events -----------------------------------------------------------------------------------------
		s.parse_events(main_boat_update['general']['events'])
		# step 5: update stuff from server response --------------------------------------------------------------------
		global_data = s.server_response['global-data']
		s.globally_paused = global_data['paused']
		s.boat_enabled = main_boat_update['general']['enabled']
		# reset flag
		s.waiting_on_server = False

	def parse_events(s, events:list) -> None:
		'''
		goes through a list of events from the server
		:param events: see simulator.ClientHandler.update.__doc__ -> client-return -> general -> events
		:return: None
		'''
		for event_lst in map(lambda str: str.split(' '), events):
			event = event_lst[0]
			args = event_lst[1:]
			assert event in ['reset', 'shipwreck', 'finished', 'collision'], f'an event from the server must be "reset", "shipwreck", "finished", or "collision". not {event}'
			if event == 'reset':
				# clear alerts
				s.alert.clear()
				# TODO: make this asynchronous
				s.setup_state_data(simulator.ProcManager.check_server_response(s.socket_client.send(json.dumps(['JOIN', {'auth': s.auth}]))))
				s.alert.add(text='reset', color=(0, 255, 0), t=10)
			if event == 'shipwreck':
				s.shipwreck()
			if event == 'finished':
				s.alert.add(text='You have reached Your destination', color=(0, 255, 0), t=10)
				s.alert.add(text=f'in {str(args[0])}' + (', a new personal record' * int(args[1])), color=(0, 255, 0), t=10)
			if event == 'collision':
				s.alert.add(text=f'{int(float(args[0]))} damage', color=(255, 0, 0), t=[None, 10][int(s.boat_enabled)])

	def img_clicked(s, e:tk.Event) -> None:
		'''
		called when the image is clicked
		:param e: event object
		:return: None
		'''
		pos = [e.x, e.y]
		s.img_label.focus_set()
		# check if mouse is on the minimap
		on_minimap, global_pos = s.renderer.img_minimap_to_global_pos(pos)
		if on_minimap and s.autopilot.enable.get():# set course
			s.autopilot.server_updates['target-pos'] = ['global-pos', extras.convert_pos(global_pos, type_=list)]
		else:# otherwise, toggle paused state
			s.toggle_paused_state()
			s.mouse_move_on_img(e)# update mouse rudder control (if enabled)

	def mouse_move_on_img(s, e:tk.Event) -> None:
		'''
		called when the mouse is moved on the image
		:param e: tkinter event object
		:return: None
		'''
		s.img_mouse_pos = [e.x, e.y]
		l = s.renderer.img_rudder_ctrl_box
		s.mouse_in_rudder_ctrl_box = e.x >= l[0] and e.y >= l[1] and e.x <= l[2] and e.y <= l[3]
		if s.mouse_in_rudder_ctrl_box and not s.paused.get() and not s.globally_paused:
			s.rudder_control.set_input('user/mouse', (e.x - (s.renderer.size[0] / 2)) / ((l[2] - l[0]) / 180))
		else:
			s.rudder_control.disable_input('user/mouse')

	def mouse_exit_img(s, e:tk.Event) -> None:
		'''
		called when the mouse leaves the image
		:param e: tkinter event object
		:return: None
		'''
		s.img_mouse_pos = None
		s.mouse_in_rudder_ctrl_box = False
		s.rudder_control.disable_input('user/mouse')

	def scroll_on_img(s, e:tk.Event) -> None:
		'''
		called when the scroll wheel is moved over the image, changes the pixel units scale
		:param e: tkinter scroll event object
		:return: None
		'''
		# stackoverflow.com/questions/17355902
		if sys.platform == 'darwin':
			scroll = e.delta
		else:
			scroll = (e.delta / 120)# * extras.sign(e.num == 1)
		scroll *= -extras.sign(s.reverse_scrolling)
		ratio = 1.2
		if scroll < 0:
			ratio = 1.0 / ratio
		s.common_pixel_units.scale(ratio=ratio)

	def key_event_img(s, e:tk.Event, pressed:bool) -> None:
		'''
		processes keyboard event on image
		:param e: tk event
		:param pressed: whether the key is being pressed or released
		:return: None
		'''
		directions = {'a': '<', 'd': '>', 'w': '^', 's': 'V'}
		if e.char in directions.keys():
			direction = directions[e.char]
			commands = {'>': (0, 8), '<': (0, -8), '^': (1, -5), 'V': (1, 5)}# sideways controls rudder (0), up/down controls sails (1)
			type_, movement = commands[direction]
			if type_ == 0:# rudder
				if pressed:
					s.rudder_control.set_input('user/keyboard', s.renderer.main_boat.rudder_angle + movement - 270)
				else:
					s.rudder_control.disable_input('user/keyboard')
			else:# sails
				if pressed:
					for _, widget in s.renderer.sheeting_sliders.items():
						widget.set(float(widget.get()) + movement)

	def set_img_size(s, size:tuple) -> tuple:
		'''
		called when the window is resized or when entering or exiting fullscreen mode, calculates new image size
		:param size: new toplevel widget size
		:return: new image render size
		'''
		new_size = tuple([max(n - 4, min_) for n, min_ in zip([size[0] - s.side_frame.winfo_width(), size[1]], s.min_img_size)])
		try:
			s.renderer.set_img_size(new_size)
		except AttributeError:
			pass
		return new_size

	def minsize(s) -> tuple:
		'''
		calculates the minimum window size
		:return: minimum size (X, Y)
		'''
		return s.min_img_size[0] + s.side_frame.winfo_width(), max(s.min_img_size[1], s.side_frame.winfo_height())

	def save_scrot(s) -> None:
		'''
		saves s.curr_img in the `scrots` folder
		:return: None
		'''
		os.chdir(extras.resources.scrots_dir)
		if s.admin:
			name = f'{str(dt.datetime.fromtimestamp(int(time.time())))}_scrot_{s.sim_name}.png'
		else:
			name = f'{s.ip}:{str(s.port)}_scrot.png'
		s.renderer.img.save(extras.validate_filename(name))
		s.alert.add('screenshot saved', (0, 255, 0), 3)

	def check_record(s, new_record:float) -> bool:
		'''
		checks if `new_record` is a new completion time record for this simulation
		:param new_record: record in seconds
		:return: whether it is a new record
		'''
		if new_record < s.record or s.record == -1:
			s.new_record = True
			s.record = new_record
			# save record
			os.chdir(extras.resources.simulations_dir)
			with open(s.sim_name + '.json') as f:
				conf = json.loads(f.read())
			conf['record'] = s.record
			with open(s.sim_name + '.json', 'w') as f:
				f.write(json.dumps(conf))
			return True
		return False

	def shipwreck(s) -> None:
		'''
		changes the state of the GUI to disable the user's control of the boat
		:return: None
		'''
		# disable controls
		s.set_controls_state(False)
		# alert
		s.alert.add(text='shipwreck', color=(255, 0, 0), t=None)

	def set_controls_state(s, state:bool) -> None:
		'''
		enables/disables all controls for the boat and autopilot
		:param state: bool
		:return: None
		'''
		widget_state = ('disabled', 'normal')[int(state)]
		# boat controls
		s.rudder_angle_scale.config(state=widget_state)
		s.renderer.set_sheeting_slider_states(state)
		# autopilot
		if not state:
			s.autopilot.enable.set(state)

	def toggle_paused_state(s, global_:bool=False, from_checkbutton:bool=False) -> None:
		'''
		toggles the paused state
		:param global_: whether to globally pause the simulation, can only be done by the admin
		:param from_checkbutton: whether this was called by the "Pause" checkbutton
		:return: None
		'''
		if global_:
			if s.admin:
				s.admin_command(['TOGGLE-PAUSE'])
			else:
				raise AssertionError('cannot toggle global paused state if not __admin__')
		else:
			if s.boat_enabled:
				if not from_checkbutton:
					s.paused.set(not s.paused.get())
				s.user_input['paused'] = s.paused.get()

	def set_sheeting_angle(s, sail_name:str, angle:int) -> None:
		'''
		puts a request to set the sheeting angle for sail `sail_name` to `angle` in the user input data
		:param sail_name: sail name
		:param angle: sheeting angle
		:return: None
		'''
		if 'sheeting-angles' not in s.user_input['boat']:
			s.user_input['boat']['sheeting-angles'] = {}
		s.user_input['boat']['sheeting-angles'][sail_name] = angle

	def quit_server(s) -> None:
		'''
		quits the server if admin
		:return: None
		'''
		s.admin_command(['QUIT'])

	def leave_server(s) -> None:
		'''
		leaves the server, only if not the process controller
		:return: None
		'''
		if not s.process_controller:
			s.quit = True

	def reset(s, global_:bool=False) -> None:
		'''
		requests a reset, this is how a reset works:
			1: this function is run, either requesting a local (only this boat) or global (all boats) reset
			2: the server resets
			3: the server update for the boat controlled by this client will have a flag telling this class to update the GUI
		:param global_: whether to reset the entire simulation, can only be done by the admin
		:return: None
		'''
		assert s.admin or not global_, 'cannot globally reset a simulation if the client is not the admin'
		if global_:
			s.admin_command(['RESET'])
		else:
			s.user_input['reset'] = True
		# clear alerts
		s.alert.clear()


class MainGUI:
	def __init__(s, master:tk.Tk):
		s.master = master
		s.frame = tk.Frame(master)
		s.frame.grid(row=0, column=0, sticky='nsew')
		s.screen_size = (s.master.winfo_screenwidth(), s.master.winfo_screenheight())
		s.window_size = (s.master.winfo_width(), s.master.winfo_height())
		# add master.wm_protocol to save space object
		s.master.wm_protocol('WM_DELETE_WINDOW', s.close)
		# bindings
		s.master.bind('<Escape>', lambda _:s.toggle_fullscreen())
		s.master.bind('<Configure>', s.resize)
		# tk vars and flags
		s.fullscreen = False
		s.screen_state = ''
		s.error = tk.StringVar()
		s.error.set('')
		s.new_sim_name = tk.StringVar()
		s.new_sim_name.set('')
		s.sim_to_delete = None
		s.public = tk.BooleanVar()
		s.public.set(False)
		# wind settings for new sim screen
		s.wind_setting_inputs = {'speed-average': [0, 100, 0.1],
			'max-gust': [0, 100, 0.1],
			'speed-variability': [0, 5, 0.1],
			'direction-variability': [0, 10, 0.1],
			'direction': [0, 359.9, 0.1]}
		# setup the GUI
		s.recreate_gui()

	def recreate_gui(s, state='home', title=None) -> None:
		'''
		sets the state of the GUI
		:param state: state, can be in:
			home: main screen, select simulation to continue playing
			new: screen to create a new simulation
			ask-delete-sim: prompt to delete or trash a simulation
			join: inputs to join another sim server
			sim-options: prompt to run/host a simulation
			running: screen for when the simulation is running
		:param title: title for s.master.wm_title()
		:return: None
		'''
		extras.dbp(f'MainGUI.recreate_gui: state: {state}, title: {str(title)}')
		if state == s.screen_state:
			return
		else:
			s.screen_state = state
		assert s.screen_state in ['home', 'new', 'ask-delete-sim', 'join', 'sim-options', 'running']
		# whether the user can resize the screen, if True the main frame will be sticky
		resizable = {'home': False, 'new': False, 'ask-delete-sim': False, 'join': False, 'sim-options': False, 'running': True}[s.screen_state]
		set_title = False
		if title != None:
			s.master.wm_title(title)
			set_title = True
		# recreate frame
		s.frame.destroy()
		del s.frame
		s.frame = tk.Frame(s.master)
		if resizable:
			s.frame.grid(row=0, column=0, sticky='nsew')
			s.master.resizable(True, True)
		else:
			s.master.minsize(0, 0)
			s.master.attributes('-fullscreen', False)
			s.master.resizable(False, False)
			s.frame.grid(row=0, column=0)
		curr_row = 0
		if s.screen_state == 'home':
			if not set_title:
				s.master.wm_title(f'{program_name} v{extras.__version__}')
			# row 0: start sim button
			tk.Button(s.frame, text='Simulation options', command=lambda: s.recreate_gui(state='sim-options')).grid(row=curr_row, column=0)
			# row 1: start sim button
			curr_row += 1
			tk.Button(s.frame, text='Join simulation', command=lambda: s.recreate_gui(state='join')).grid(row=curr_row, column=0)
			# row 2: new sim button
			curr_row += 1
			tk.Button(s.frame, text='Create new simulation', command=lambda: s.recreate_gui(state='new')).grid(row=curr_row, column=0)
			# row 3: open docs button
			curr_row += 1
			tk.Button(s.frame, text='Open documentation', command=extras.open_docs).grid(row=curr_row, column=0)
			# row 4: error message
			curr_row += 1
			msg = 'No errors'
			s.error_box = tk.Text(s.frame, fg='green', width=len(msg), height=1)
			s.error_box.grid(row=curr_row, column=0)
			s.error_box.insert(tk.END, msg)
		if s.screen_state == 'new':
			if not set_title:
				s.master.wm_title(f'New simulation - {program_name} v{extras.__version__}')
			# setup GUI
			# row 0: new sim GUI
			s.new_sim_frame = tk.Frame(s.frame)
			s.new_sim_frame.grid(row=curr_row, column=0)
			# row 1: buttons
			curr_row += 1
			s.buttons_frame = tk.Frame(s.frame)
			s.buttons_frame.grid(row=curr_row, column=0)
			tk.Button(s.buttons_frame, text='cancel', command=s.recreate_gui).grid(row=0, column=0)
			s.new_sim_button = tk.Button(s.buttons_frame, text='create', command=s.new, state='disabled')
			s.new_sim_GUI = GUIs.NewSim(s.new_sim_frame, s.wind_setting_inputs, lambda valid: s.new_sim_button.config(state=['disabled', 'normal'][int(valid)]))
			s.new_sim_button.grid(row=0, column=1)
		if s.screen_state == 'ask-delete-sim':
			if not set_title:
				s.master.wm_title(f'Delete simulation - {program_name} v{extras.__version__}')
			# row 0: label
			tk.Label(s.frame, text=f'Are you sure that you want to delete the simulation file "{s.sim_to_delete}.json"?').grid(row=curr_row, column=0)
			# row 1: options frame
			curr_row += 1
			s.delete_sim_options_frame = tk.Frame(s.frame)
			s.delete_sim_options_frame.grid(row=curr_row, column=0)
			# col 0: options
			tk.Button(s.delete_sim_options_frame, text='Delete', command=lambda:s.del_sim(ask=False)).grid(row=0, column=0)
			tk.Button(s.delete_sim_options_frame, text='Send to trash', command=s.trash_sim).grid(row=0, column=1)
			tk.Button(s.delete_sim_options_frame, text='Cancel', command=s.recreate_gui).grid(row=0, column=2)
		if s.screen_state == 'join':
			if not set_title:
				s.master.wm_title(f'Join simulation - {program_name} v{extras.__version__}')
			# setup GUI
			# row 0: join sim frame
			s.join_sim_frame = tk.Frame(s.frame)
			s.join_sim_frame.grid(row=curr_row, column=0)
			# join sim GIU
			s.join_sim_GUI = GUIs.AskJoinSimulation(frame=s.join_sim_frame, join_callback=lambda: s.start_sim('join'), quit_callback=s.recreate_gui)
		if s.screen_state == 'sim-options':
			if not set_title:
				s.master.wm_title(f'Start simulation - {program_name} v{extras.__version__}')
			# row 0: sims listbox
			s.sim_lst_frame = tk.Frame(s.frame)
			s.sim_lst_frame.grid(row=curr_row, column=0)
			# row 1: sim options frame
			curr_row += 1
			s.sim_options_frame = tk.Frame(s.frame)
			s.sim_options_frame.grid(row=curr_row, column=0)
			tk.Button(s.sim_options_frame, text='Start', command=lambda: s.start_sim('host'), state='disabled').grid(row=0, column=0)
			tk.Button(s.sim_options_frame, text='Reset', command=s.reset_sim, state='disabled').grid(row=0, column=1)
			tk.Button(s.sim_options_frame, text='Delete', command=s.del_sim, state='disabled').grid(row=0, column=2)
			# init simulation list GUI
			s.sim_lst_GUI = GUIs.ResourceList(frame=s.sim_lst_frame, type_='sims', change_valid_callback=lambda valid: [widget.config(state=['disabled', 'normal'][int(valid)]) for widget in s.sim_options_frame.winfo_children()])
			# row 2: public checkbutton
			curr_row += 1
			s.public.set(False)
			s.public_checkbutton = tk.Checkbutton(s.frame, text='Public', variable=s.public)
			s.public_checkbutton.grid(row=curr_row, column=0)
			# row 3: public options
			curr_row += 1
			s.public_frame_row = curr_row
			# notice I didn't use .grid()
			s.public_options_frame = tk.Frame(s.frame)
			# label
			tk.Label(s.public_options_frame, text='Port to host server').grid(row=0, column=0)
			# port entry
			s.port_entry = tk.Entry(s.public_options_frame, validatecommand=extras.validate_port)
			s.port_entry.insert(0, str(extras.DEFAULT_PORT))
			s.port_entry.grid(row=0, column=1)
			# add change state callback to checkbutton to hide or show this frame
			s.public_checkbutton.config(command=lambda: s.set_public_option_state(s.public.get()))
			# row 4: cancel button
			curr_row += 1
			tk.Button(s.frame, text='Cancel', command=s.recreate_gui).grid(row=curr_row, column=0)
		if s.screen_state == 'running':
			if not set_title:
				s.master.wm_title(f'{program_name} v{extras.__version__}')
			# row 0: frame for the space object
			s.sim_frame = tk.Frame(s.frame)
			s.sim_frame.grid(row=curr_row, column=0, sticky='nsew')
			s.frame.grid_rowconfigure(0, weight=1)
			s.frame.grid_columnconfigure(0, weight=1)
		if resizable:
			if not set_title:
				s.master.wm_title(f'{program_name} v{extras.__version__}')
			s.master.grid_rowconfigure(0, weight=1)
			s.master.grid_columnconfigure(0, weight=1)
			s.master.geometry(f'{str(s.screen_size[0] - 100)}x{str(s.screen_size[1] - 100)}+50+50')
		else:
			s.set_min_size()

	def set_min_size(s) -> None:
		'''
		sets the master to it's minimum size and sets the minimum size
		:return: None
		'''
		# don't know why, but the grid weight matters
		s.master.grid_rowconfigure(0, weight=0)
		s.master.grid_columnconfigure(0, weight=0)
		# create the widgets so the frame size will be correct
		s.master.update_idletasks()
		# set to correct size
		s.master.geometry(f'{str(s.frame.winfo_width())}x{str(s.frame.winfo_height())}')

	def set_public_option_state(s, state:bool) ->None:
		'''
		sets the visibility of the s.public_options_frame frame
		:param state: whether to show the frame
		:return: None
		'''
		assert s.screen_state == 'sim-options', 'this method can only be called when the screen is in the "sim-options" state'
		[s.public_options_frame.grid_forget, lambda: s.public_options_frame.grid(row=s.public_frame_row, column=0)][int(state)]()
		s.set_min_size()

	def start_sim(s, mode) -> None:
		'''
		starts a simulation
		:param mode: sim start mode, can be "host", or "join"
		:return: None
		'''
		assert mode in ['host', 'join']
		s.error.set('')# reset error label
		screen_size = [s.master.winfo_width(), s.master.winfo_height()]
		if mode == 'join':
			# get data from widgets
			user_inputs = s.join_sim_GUI.get_data()
			# set screen
			s.recreate_gui(state='running', title=f'{user_inputs["ip"]}:{user_inputs["port"]} - {program_name} v{extras.__version__}')
			# client init args
			args = [
				s.sim_frame,
				screen_size,
				False,
				True
			]
			kwargs = {
				'port': int(user_inputs['port']),
				'ip': user_inputs['ip'],
				'username': user_inputs['username'],
				'password': user_inputs['password'],
				'sim_password': user_inputs['sim-password']
			}
		if mode == 'host':
			# get data from user
			sim_name = s.sim_lst_GUI.get()
			public = s.public.get()
			if public:
				port_str = s.port_entry.get().strip()
				if not extras.validate_port(port_str):
					s.recreate_gui()
					s.show_error('server port must be a positive integer between 0 - 65,535')
					return
				port = int(port_str)
			# screen title
			s.recreate_gui(state='running', title=f'{sim_name} - {program_name} v{extras.__version__}')
			# client init args
			args = [
				s.sim_frame,
				screen_size,
				True,
				public
			]
			kwargs = {
				'sim_name': sim_name,
			}
			if public:
				kwargs['port'] = port
		# attempt to init client
		try:
			s.sim_client = SimClient(*args, **kwargs)
		except Exception:
			s.recreate_gui()
			s.show_error(f'exception while initiating SimClient:\n{traceback.format_exc()}')
			return
		s.master.update_idletasks()
		s.master.minsize(*s.sim_client.minsize())
		s.sim_client.set_img_size(s.master.size())
		if mode == 'host' and public:
			s.master.wm_title(f'{sim_name} on {s.sim_client.ip}:{str(s.sim_client.port)} - {program_name} v{extras.__version__}')
		s.sim_iteration()

	def reset_sim(s) -> None:
		'''
		resets the selected simulation
		:return: None
		'''
		assert s.screen_state == 'sim-options'
		sim = simulator.Simulator(sim_name=s.sim_lst_GUI.get(), admin_code=1)
		sim.reset()
		sim.save_sims = True
		sim.save()

	def del_sim(s, ask:bool=True) -> None:
		'''
		deletes or asks to delete the selected simulation
		:param ask: whether to ask the user before deleting the simulation file
		:return: None
		'''
		if ask:
			assert s.screen_state == 'sim-options'
			s.sim_to_delete = s.sim_lst_GUI.get()
			s.recreate_gui(state='ask-delete-sim')
		else:
			os.remove(os.path.join(extras.resources.simulations_dir, s.sim_to_delete + '.json'))
			s.recreate_gui()

	def trash_sim(s) -> None:
		'''
		sends the simulation `s.sim_to_delete` to the trash
		:return: None
		'''
		send2trash(os.path.join(extras.resources.simulations_dir, s.sim_to_delete + '.json'))
		s.recreate_gui()

	def new(s):
		'''
		creates a new simulation, can only be called when the screen has been set to "new"
		:return: None
		'''
		new_sim_config = s.new_sim_GUI.get()
		boat = new_sim_config['boat']
		map = new_sim_config['map']
		name = new_sim_config['name']
		password = new_sim_config['password']
		wind_settings = new_sim_config['wind']
		rtrn = simulator.Simulator.new_sim(boat, map, name, wind_settings, password)
		s.recreate_gui()
		if not rtrn[0]:
			s.show_error(f'while creating new simulation:\n{rtrn[1]}')

	def sim_iteration(s):
		'''
		runs one frame of the simulation
		:return: None
		'''
		# check if it has been quit
		if s.sim_client.quit:
			s.sim_client.quit_server()
			s.recreate_gui()
			return
		# check callback errors
		if len(s.sim_client.callback_errors) != 0:
			s.sim_client.quit_server()
			s.recreate_gui()
			s.show_error(f'Error(s) in callback function(s):\n' + ('\n---------------\n'.join(s.sim_client.callback_errors)))
			return
		# update simulation
		try:
			s.sim_client.update()
		except Exception:
			s.sim_client.quit_server()
			s.recreate_gui()
			s.show_error(f'Exception while running SimClient.update:\n{traceback.format_exc()}')
			return
		# update idletasks
		s.master.update_idletasks()# so that the near-zero delay time doesn't get in the way of this
		# schedule next frame
		s.master.after(1, s.sim_iteration)

	def show_error(s, error:str) -> None:
		'''
		shows `error` on the GUI
		:param error: string to show or None
		:return: None
		'''
		msg = f'ERROR: {error}'
		s.error_box.delete("1.0", tk.END)
		s.error_box.insert(tk.END, msg)
		s.error_box.config(fg='red', width=max([len(l) for l in msg.split('\n')]), height=len(msg.split('\n')))
		# set to correct size
		s.master.update_idletasks()
		s.master.geometry(f'{str(s.frame.winfo_width())}x{str(s.frame.winfo_height())}')

	def toggle_fullscreen(s) -> None:
		'''
		toggles fullscreen mode, see: stackoverflow.com/questions/7966119
		:return: None
		'''
		s.fullscreen = not s.fullscreen
		s.master.attributes('-fullscreen', s.fullscreen)
		try:
			if s.fullscreen:
				s.sim_client.alert.add('Press Esc to exit fullscreen', (0, 255, 0), 5)
		except AttributeError:
			pass

	def resize(s, e:tk.Event) -> None:
		'''
		called when the window is resized or when entering or exiting fullscreen mode
		:param e: event object
		:return: None
		'''
		if s.window_size == (e.width, e.height):
			return
		s.window_size = (e.width, e.height)

	def close(s):
		'''
		called when the close button is pressed - closes window
		:return: None
		'''
		try:
			s.sim_client.quit_server()
		except AttributeError:
			pass
		s.master.destroy()


def main() -> int:
	root = tk.Tk()
	root.wm_title(f'{program_name} v{extras.__version__}')
	main_gui = MainGUI(root)
	print('starting the tkinter GUI')
	try:
		root.mainloop()
	except KeyboardInterrupt:
		main_gui.close()
	print('END')
	return 0

if __name__ == '__main__':
	sys.exit(main())
