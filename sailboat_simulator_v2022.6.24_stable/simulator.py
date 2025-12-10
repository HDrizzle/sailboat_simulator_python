#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  simulator.py
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
import math, os, json, time, copy, traceback, random, re, socket, threading
import multiprocessing as mp

# 3rd-party, from PyPi
import tkinter as tk
from pymunk.vec2d import Vec2d# very useful
from shapely import ops
from shapely.geometry import *

# from CWD
import GUIs
import extras
import constants as csnts


# classes
class FlatObjectPhysics:
	'''
	class for modeling a flat object in a fluid (meant to be a base class for things like sails, rudder, etc)
	'''
	def __init__(s, len_:float, COE_len:float, density:float, area:float, angle:float=0):
		'''
		init
		:param len_: object length
		:param COE_len: distance between the pivot and the COE (Center Of Effort)
		:param density: fluid density
		:param area: object area
		:param angle: starting angle
		'''
		# save params
		s.len_ = len_
		s.COE_len = COE_len
		s.density = density
		s.area = area
		s.angle = angle
		s.prev_angle = s.angle
		# other stuff
		s.input_force = False
		s.limits_reached = False

	def get_force(s, fluid_momentum:Vec2d) -> Vec2d:
		'''
		gets the force on the object
		:param fluid_momentum: fluid momentum relative to object
		:return: force vector
		'''
		return extras.sideways_drag_force_on_flat_object(s.density, fluid_momentum, s.area, s.angle)

	def set_angle(s, angle:float) -> None:
		'''
		sets the angle
		:param angle: angle in degrees, if None, s.force is set to False
		:return: None
		'''
		assert type(angle) in [int, float] or angle is None
		if type(angle) in [int, float]:
			s.angle = angle
			s.input_force = True
		else:
			s.input_force = False

	def _update(s, sim_t:float, fluid_momentum:Vec2d, travel:list=None) -> list:
		'''
		updates the object
		:param sim_t: simulation frame time since last update
		:param fluid_momentum: fluid momentum relative to the object
		:param travel: optional 2 item list defining the clockwise (-) and anticlockwise (+) travel limits
		:return: [(Vec2d): center of effort, (Vec2d): force, (bool): whether the object hit the travel limits]
		'''
		# convert fluid momentum to sideways fluid momentum relative to the object
		sideways_fluid_momentum = fluid_momentum.rotated_degrees(-(s.angle - 90) % 360).x
		# change angle
		s.limits_reached = False
		if s.input_force:
			force = True
		else:
			change = -((sideways_fluid_momentum / s.COE_len) / math.pi) * 180 * sim_t
			s.angle += change
			s.angle %= 360
			# check if angle is outside limits
			# NOTE: this may not work if the angle has changed 180 or more degrees
			if travel is not None:
				assert type(travel) in [list, tuple] and len(travel) == 2
				change_sign = extras.sign(change)
				curr_limit_angle = travel[(change_sign + 1) // 2]
				if not extras.is_angle_between(s.angle, *travel):# check if s.angle isn't between the travel limit angles
					if change != 0:
						s.angle = curr_limit_angle
						s.limits_reached = True
					force = True
				else:
					force = False
			else:
				force = False
		s.prev_angle = s.angle
		# calculate force and center of effort
		return [Vec2d(s.COE_len, 0).rotated_degrees(s.angle), s.get_force(fluid_momentum) * int(force), s.limits_reached]


class SuperSail:
	'''
	class for graphics and physics
	'''
	def __init__(s, static_config:dict, config:dict):
		'''
		init
		:param static_config: data about the sail that isn't changed by the simulation
			area: sail area in ft^2
			center-of-effort: distance between the center of effort of the sail and the tack
			tack: where the tack is mounted on the boat (Y coord only, local coords)
			foot-len: length of the foot of the sail
		:param config: data about the sail that may be changed by the simulation, that has to be saved
			angle: angle of the sail, 270 is strait
			sheeting-angle: max angle diff from 270 that the sheet will allow
		'''
		# static config data
		s.area = static_config['area']
		s.center_of_effort = static_config['center-of-effort']
		s.tack = static_config['tack']
		s.foot_len = static_config['foot-len']
		# simulation specific data
		s.load_config(config)
		# placeholders
		s.sheet_tension = False
		s.turbo_boost = False
		s.force_vector_color = (0, 255, 0)

	def load_config(s, d:dict) -> None:
		'''
		loads sim config data
		:param d: sim config data
		:return: None
		'''
		s.default_config = {
			'angle': 0,
			'sheeting-angle': 90,
			'force': [0, 0]
		}
		d = extras.validate_config_dict(d=d, default=s.default_config, types={key: type(value) for key, value in s.default_config.items()})
		s.angle = d['angle']
		s.sheeting_angle = d['sheeting-angle']
		s.force = Vec2d(*d['force'])

	def serializable(s) -> dict:
		'''
		opposite of s.load_config()
		:return: dict to be saved in the simulation file
		'''
		return {
			'angle': s.angle,
			'sheeting-angle': s.sheeting_angle,
			'force': list(s.force)
		}


class Sail(SuperSail, FlatObjectPhysics):
	'''
	class for modeling the physics of a sail
	'''
	def __init__(s, static_config:dict, config:dict):
		'''
		init
		:param static_config: same as superclass
		:param config: same as superclass
		'''
		# init superclasses
		SuperSail.__init__(s, static_config, config)
		FlatObjectPhysics.__init__(s, s.foot_len, s.center_of_effort, csnts.density.water, s.area, s.angle)

	def update(s, sim_t:float, wind:Vec2d) -> list:
		'''
		calculates force on the boat hull with the wind speed
		:param sim_t: simulation time
		:param wind: wind vector (apparent wind)
		:return: [force vector, center of effort] (all in local coords)
		'''
		s.curr_center_of_effort, s.force, s.sheet_tension = s._update(sim_t, wind, [270 - s.sheeting_angle, 270 + s.sheeting_angle])
		s.curr_center_of_effort += Vec2d(0, s.tack)
		if s.turbo_boost:# easter egg
			s.force = Vec2d(0, s.force.length * 5)
		return [s.force, s.curr_center_of_effort]


class SuperSailboat:
	'''
	class for graphics and vector conversion
	'''
	force_keys = ['hull-water-drag', 'hull-air-drag', 'sails-total', 'rudder', 'total']
	default_forces = {key: [[0, 0], [0, 0]] for key in force_keys}

	def __init__(s, time_logger:extras.TimeLogger, config:dict, static_config:dict):
		'''
		NOTE: "boat/local" coordinates are in reference to the boats global position and angle
		NOTE: when the boat's rotation is 0 degrees, this means that (local) +Y would be facing to (global) 0 degrees
		NOTE: self.update_settings() must be called before this can be used
		class to represent the boat
		:param time_logger: time logger object
		:param config: dictionary from client dict from simulation file under "boat"
		:param static_config: see s.setup_static_specs.__doc__
		'''
		# save params
		s.time_logger = time_logger
		# flags and defaults
		s.sanity_limits_reached = False
		# load static config data
		s.setup_static_specs(static_config)
		# setup config
		s.setup_config(config)
		# turbo booster easter egg
		re.IGNORECASE = True
		turbo_booster_re = re.compile('''turbo[ \-_]?booster''')
		s.turbo_booster_enable = False
		for sail_name in s.sails.keys():
			if re.search(turbo_booster_re, sail_name) != None:
				s.turbo_booster_enable = True
				s.sails[sail_name].turbo_boost = True
		# create shapely poly object for perimeter
		s.shapely_perim = Polygon(s.perimeter)
		# create perimeter max radius, for render distance calculation
		s.perim_max_radius = max([Vec2d(*point_lst).length for point_lst in s.perimeter])

	def setup_static_specs(s, static_config:dict) -> None:
		'''
		loads static specs for boat type `type_` from corresponding JSON file in the boat_specs dir
		:param static_config: static config dictionary
		:return: None
		'''
		key_requirements = {
			'perimeter': list,# list of lists of coords representing the perimeter of the boat, must be anticlockwise
			'center-of-lateral-resistance': float,# the Y-coord (local coords) of the center of lateral resistance
			'forward-drag': float,# drag moving forward
			'sideways-drag': float,# drag moving sideways
			'scale': float,# scale to use for drag function
			'boat-air-drag': float,# wind drag on the rest of the boat (excluding sails)
			'max-draft': float,# min depth of water the boat can float in
			'rudder-pivot': float,# the Y-coord (local coords) of the rudder pivot
			'rudder-area': float,# the underwater area of the rudder from the side
			'rudder-center-of-effort': float,# feet between the rudder's pivot and the rudder's center of effort
			'rudder-len': float,# length of the rudder from pivot, only used for graphics
			'mass': float,# net mass of the boat
			'moment': float,# angular mass of the boat in degrees/second/second/foot-pound
			'angular-drag': float,# angular drag (without rudder)
			'max-hull-durability': float,# max hull durability
			'upwind-max-wind-angle': float,# most efficient angle of the boat from the wind to go upwind
			'upwind-max-total-leeway': float,# angle between the wind and the direction of the boat's momentum when going upwind-max-wind-angle from the wind
			'sails-static': dict}# dictionary, {sail name:dict to be used for the first arg in sail_class.__init__}
		s.static_config = static_config
		# check that every key in `key_requirements` is in `s.static_config.keys()`
		for key in key_requirements.keys():
			if key not in s.static_config.keys():
				raise KeyError(f'missing key "{key}" in the static config JSON file for this boat')
		# iterate over `s.static_config`
		for key, value in s.static_config.items():
			if key in key_requirements.keys():
				# check that `value` is of the right type
				try:
					key_requirements[key](value)
				except Exception:
					raise KeyError(False, f'invalid key "{key}" in the static config JSON file for this boat')
				# save it to self
				s.__setattr__(key.replace('-', '_'), value)
		# create local drag vector
		s.local_drag = Vec2d(s.sideways_drag, s.forward_drag)

	def setup_config(s, config:dict, setup_sails:bool=True) -> None:
		'''
		creates attributes from config from a simulation
		:param config: simulation boat config that has been validated
		:param setup_sails: whether to setup the sails, this is for the sailboat renderer subclass which uses different sail types
		:return: None
		'''
		# required and default config keys/values
		s.required_config_keys = ['type', 'pos', 'angle', 'sails']
		# NOTE: these need to be set every time because values that are passed by reference may be overwritten
		s.default_config = {'velocity': Vec2d(0, 0), 'angular-velocity': 0, 'rudder-enable': True, 'rudder-angle': 270, 'forces': {}}
		# types
		s.config_types = {
			'type': str,
			'pos': list,
			'velocity': list,
			'angular-velocity': float,
			'rudder-angle': float,
			'hull-durability': float,
			'rudder-enable': bool,
			'sails': dict,
			'forces': dict
		}
		# check that all the required keys exist
		config = extras.validate_config_dict(config, default=s.default_config, required_keys=s.required_config_keys, types=s.config_types)
		# set attrs
		s.type_ = config['type']
		s.pos = Vec2d(*config['pos'])
		assert not (True in [str(n) == 'nan' for n in list(s.pos)]), 'position has 1 or more NaN'
		s.prev_pos = copy.deepcopy(s.pos)# for object tunneling detection purposes
		s.angle = config['angle']
		s.velocity = Vec2d(*config['velocity'])
		s.angular_velocity = config['angular-velocity']
		s.hull_durability = config['hull-durability']
		s.rudder_enable = config['rudder-enable']
		s.rudder_angle = config['rudder-angle']
		if setup_sails:
			# create sail objects
			sail_config = config['sails']
			s.sails = {name: Sail(static_conf_dict, sail_config[name]) for name, static_conf_dict in s.sails_static.items()}
		# forces
		tmp_forces = extras.validate_config_dict(
			d=config['forces'],
			default=s.default_forces,
			types={key: list for key in s.force_keys}
		)
		s.forces = {name: [Vec2d(*v) for v in f] for name, f in tmp_forces.items()}
		# leeway
		s.leeway_angle = abs(90 - s.local_velocity().angle_degrees)

	def upwind_speed(s) -> float:
		'''
		calculates the boats current upwind speed
		:return: upwind speed
		'''
		return Vec2d(0, s.velocity.length).rotated_degrees(s.wind_momentum_angle()).y

	def convert_vector(s, v, convert_to:str, unit_type:str='angle', body_data:dict=None) -> Vec2d:
		'''
		universal local/global vector convertor
		:param v: vector to be converted
		:param convert_to: can be 'local' or 'global'
		:param unit_type: type of value to convert, can be "angle", "pos", or "velocity"
		:param body_data: data about the body being used, all keys will default to attributes defined in this class:
			angle: body's angle (degrees)
			pos: body's position
			velocity: body's global velocity
		:return: converted vector
		'''
		v = extras.convert_pos(v, Vec2d)
		assert convert_to in ['local', 'global'], f'convert_to must be "local" or "global", not "{convert_to}"'
		assert unit_type in ['angle', 'pos', 'velocity'], f'unit_type must be "angle", "pos", or "velocity", not "{unit_type}"'
		if body_data is None:
			body_data = {}
		body_data = {
			'angle': s.angle,
			'pos': s.pos,
			'velocity': s.velocity,
			**body_data
		}
		instance_func = lambda v: s.convert_vector(v=v, convert_to=convert_to, unit_type='angle', body_data=body_data)
		if convert_to == 'global':# local to global
			if unit_type == 'angle':# plain vector
				return v.rotated_degrees((body_data['angle'] - 90) % 360)
			if unit_type == 'pos':
				return instance_func(v) + body_data['pos']
			if unit_type == 'velocity':
				return instance_func(v) + body_data['velocity']
		else:# global to local
			if unit_type == 'angle':# plain vector
				return v.rotated_degrees(-(body_data['angle'] - 90) % 360)
			if unit_type == 'pos':
				return instance_func(v - body_data['pos'])
			if unit_type == 'velocity':
				return instance_func(v - body_data['velocity'])

	def geom_to_local(s, geom, body_data:dict=None):
		'''
		NOTE: DO NOT USE FOR SUBCLASS Sailboat BECAUSE THIS USES VARIABLES DEFINED IN THE SUPERCLASS AND NOT UPDATED DURING THE SIMULATION
		converts shapely geometry object `geom` to one in boat local coordinates
		:param geom: geom object
		:return: new geom object
		'''
		return ops.transform(lambda x, y: tuple(s.convert_vector(v=[pos for pos in [x, y]], convert_to='local', unit_type='pos', body_data=body_data)), geom)

	def local_velocity(s, body_data:dict=None) -> Vec2d:
		'''
		shortcut to get the local velocity
		:param body_data: same as s.convert_vector
		:return: local velocity
		'''
		return -s.convert_vector(v=(0, 0), convert_to='local', unit_type='velocity', body_data=body_data)

	@staticmethod
	def get_new_dict(boat_name:str, map_name:str=None) -> dict:
		'''
		creates a dictionary to be used for the "boat" key in a new simulation JSON file
		:param boat_name: boat name to make config dict for
		:param map_name: name of map being used
		:return: dictionary
		'''
		d = {
			'type': boat_name,
			'velocity': [0, 0],
			'angle': 90,
			'angular-velocity': 0,
			'rudder-angle': 270,
			'rudder-enable': True,
			'forces': Sailboat.default_forces
		}
		# boat-specific keys
		os.chdir(extras.resources.boat_dir)
		with open(boat_name + '.json') as f:
			conf = json.loads(f.read())
		d['sails'] = {sn: {'angle': 270, 'sheeting-angle': 90} for sn in conf['sails-static'].keys()}
		d['hull-durability'] = conf['max-hull-durability']
		# map-specific keys
		if not (map_name is None):
			os.chdir(extras.resources.maps_dir)
			with open(map_name + '.json') as f:
				conf = json.loads(f.read())
			d['pos'] = conf['start']# set position to the map's starting point
		else:
			d['pos'] = [0, 0]
		return d

	@staticmethod
	def static_config_template() -> dict:
		'''
		template for static config dictionary
		:return: JSON serializable dictionary
		'''
		return {
			'perimeter': [[1, -3], [0, 3], [-1, -3]],
			'center-of-lateral-resistance': 0,
			'forward-drag': 0.02,
			'sideways-drag': 4,
			'scale': 3,
			'boat-air-drag': 0.1,
			'max-draft': 0.5,
			'rudder-pivot': -3,
			'rudder-area': 1.2,
			'rudder-center-of-effort': 0.35,
			'rudder-len': 0.7,
			'mass': 1000,
			'moment': 500,
			'angular-drag': 0,
			'max-hull-durability': 1000,
			'upwind-max-wind-angle': 66,
			'upwind-max-total-leeway': 73.7,
			'sails-static': {
				'main': {'area': 10, 'center-of-effort': 2.5, 'tack': 1, 'foot-len': 4},
				'jib': {'area': 4, 'center-of-effort': 0.5, 'tack': 3, 'foot-len': 2}
			}
		}


class Sailboat(SuperSailboat):
	'''
	class for simulating a single sailboat
	'''
	def __init__(s, time_logger:extras.TimeLogger, config:dict, settings:dict, starting_wind:Vec2d=Vec2d(0, 0)):
		'''
		NOTE: "boat/local" coordinates are relative to the boats global position and angle
		NOTE: when the boat's rotation is 0 degrees, this means that (local) +Y would be facing to (global) 0 degrees
		:param time_logger: same as superclass
		:param config: same as superclass
		:param settings: same as superclass
		:param starting_wind: current simulation wind
		'''
		# settings
		s.update_settings(settings)
		# flags and defaults
		s.sanity_limits_reached = False
		s.leeway_angle = 0
		s.physics_state_attrs = ['pos', 'angle', 'velocity', 'angular_velocity', 'torque']
		s.recorded_physics_state = {}
		s.torque = 0
		# get static specs
		os.chdir(extras.resources.boat_dir)
		with open(config['type'] + '.json') as f:
			static_config = json.loads(f.read())
		# init superclass
		super().__init__(time_logger, config, static_config)
		# create rudder object
		s.rudder = FlatObjectPhysics(s.rudder_len, s.rudder_center_of_effort, csnts.density.water, s.rudder_area, config['rudder-angle'])
		s.rudder_input_manager = extras.RudderInput(['internal', 'client', 'autopilot'], rudder=s.rudder)
		s.rudder_input_manager.set_input('internal', s.rudder_angle - 270)
		s.rudder_input_manager.disable_input('internal')
		# general setup
		s.setup_general(config)
		# record physics state
		s.record_state()
		# update self to set some variables
		s.update(starting_wind, 0, {})

	def setup_general(s, dynamic_config:dict) -> None:
		'''
		does stuff needed for __init__ and resetting the simulation
		:param dynamic_config: config from simulation file
		:return: None
		'''
		# setup config
		s.setup_config(dynamic_config)
		# set rudder's angle
		s.rudder.set_angle(s.rudder_angle)

	def update_settings(s, d:dict) -> None:
		'''
		updates settings
		:param d: simulation settings
		:return: None
		'''
		s.sanity_limits = d['sanity-limits']

	def update_forces(s, t:float) -> None:
		'''
		updates translational forces in s.forces and the total torque (s.torque)
		:param t: time step
		:return: None
		'''
		local_velocity = s.local_velocity_subclass()
		# update sails
		sail_data = s.get_sail_force(t)
		sail_forces = [l[0] for l in sail_data]
		sail_centers_of_effort = [l[1] for l in sail_data]
		# get sail center of effort and force
		sails_total_force, _, sails_total_center_of_effort = extras.force_torque_coe(sail_forces, sail_centers_of_effort)
		s.forces['sails-total'] = [sails_total_center_of_effort, sails_total_force]
		# calculate water drag force
		s.forces['hull-water-drag'] = Vec2d(0, s.center_of_lateral_resistance), -Vec2d(*[extras.drag(speed, drag_c, csnts.density.water, s.scale) for speed, drag_c in zip(list(local_velocity), [s.sideways_drag, s.forward_drag])])
		# calculate air drag force
		s.forces['hull-air-drag'] = Vec2d(0, 0), s.wind * extras.drag(s.wind.length, s.boat_air_drag, csnts.density.air, s.scale)
		# get rudder center of effort and force
		if s.rudder.area > 0:
			curr_rudder_center_of_effort, rudder_force, _ = s.rudder._update(s.frame_t, Vec2d(-((((Vec2d(0, s.rudder_pivot) + Vec2d(s.rudder_center_of_effort, 0).rotated_degrees(s.rudder.angle)).length * s.angular_velocity * math.pi) / 180) + local_velocity.x), -(local_velocity.y)), [180, 0])
			curr_rudder_center_of_effort += Vec2d(0, s.rudder_pivot)
		else:
			curr_rudder_center_of_effort, rudder_force = [Vec2d(0, 0) for _ in range(2)]
		s.forces['rudder'] = [curr_rudder_center_of_effort, rudder_force]
		# get total local force, torque, and total local center of effort
		total_local_force, s.torque, total_local_center_of_effort = extras.force_torque_coe(
			*[[s.forces[f][i] for f in ['sails-total', 'hull-water-drag', 'hull-air-drag', 'rudder']] for i in [1, 0]]
		)
		s.forces['total'] = [total_local_center_of_effort, total_local_force]
		# add angular drag to torque
		s.torque += extras.angular_drag(s.angular_velocity, s.angular_drag, csnts.density.water, s.scale)

	def update(s, wind:Vec2d, frame_t, user_input:dict) -> None:
		'''
		updates everything in the boat object
		:param wind: real (global) wind vector
		:param frame_t: time since last update
		:param user_input: user input dict:
			rudder: rudder angle
			sheeting-angles:
				<sail-name>: new sheeting angle
		:return: None
		'''
		# save params
		s.frame_t = frame_t
		s.global_wind = wind
		# parse user input
		# rudder
		if 'rudder' in user_input.keys():
			rudder_angle = user_input['rudder']
			assert type(rudder_angle) in [int, float] and -90 <= rudder_angle <= 90, 'rudder angle must be a number between -90 and 90'
			s.rudder_input_manager.set_input('client', rudder_angle)
		else:
			s.rudder_input_manager.disable_input('client')
		# sheeting angles
		if 'sheeting-angles' in user_input.keys():
			sheeting_angles = user_input['sheeting-angles']
			# assertions
			assert type(sheeting_angles) == dict, 'sheets must be dict'
			# update sails
			for sail_name, sheeting_angle in sheeting_angles.items():
				assert type(sail_name) == str
				assert sail_name in s.sails.keys()
				assert type(sheeting_angle) in [int, float] and 0 <= sheeting_angle <=90
				s.sails[sail_name].sheeting_angle = sheeting_angle
		# update physics, updates twice with half the time step each, then averages the results
		s.prev_pos = copy.deepcopy(s.pos)# for object tunneling detection purposes
		s.update_physics(s.frame_t / 2)
		s.record_state()
		s.update_physics(s.frame_t / 2)
		s.average_state()
		s.update_physics(0)# last time to correct local wind and forces
		# see bug fix for 2021-12-25
		s.angle %= 360
		# leeway
		s.leeway_angle = abs(90 - s.local_velocity_subclass().angle_degrees)

	def get_sail_force(s, t:float) -> list:
		'''
		gets force and and center of effort (local coords) from sails
		:param t: time step
		:return: [[force vector:Vecd2d, center of effort:Vec2d] for each sail]
		'''
		return [sail.update(t, s.wind) for _, sail in s.sails.items()]

	def update_physics(s, t:float, check_sanity_limits:bool=True) -> None:
		'''
		:param t: time step
		:param check_sanity_limits: weather to run s.check_sanity_limits
		:return: None
		'''
		# get apparent wind
		s.wind = s.convert_vector_subclass(v=s.global_wind, convert_to='local', unit_type='velocity')
		# update forces
		s.update_forces(t)
		TFA = s.convert_vector_subclass(v=s.forces['total'][1], convert_to='global')
		# update body physics
		s.velocity += (TFA * t) / s.mass
		s.angular_velocity += (s.torque * t) / s.moment
		s.pos += s.velocity * t
		s.angle += s.angular_velocity * t
		# check sanity limits
		if check_sanity_limits:
			s.check_sanity_limits()
		s.leeway_angle = abs(extras.diff_between_angles(s.local_velocity_subclass().angle_degrees, 90))

	def record_state(s) -> None:
		'''
		records physics state attributes to be used for averaging
		:return: None
		'''
		s.recorded_physics_state = {name: s.__getattribute__(name) for name in s.physics_state_attrs}

	def average_state(s) -> None:
		'''
		averages the current physics state with the recorded one in `s.recorded_physics_state`
		:return: None
		'''
		for name in s.physics_state_attrs:
			old_value = s.recorded_physics_state[name]
			curr_value = s.__getattribute__(name)
			new_value = (old_value + curr_value) / 2
			s.__setattr__(name, new_value)

	def check_sanity_limits(s) -> None:
		'''
		TODO: FIX: sanity limits don't get reported
		checks that the boat's physics attributes are within the sanity limits
		:return: None
		'''
		# check sanity limits
		s.sanity_limits_reached = False
		# speed
		if s.velocity.length >= s.sanity_limits['velocity']:
			s.sanity_limits_reached = True
			s.velocity = Vec2d(0, 0)
		# rotational speed
		if abs(s.angular_velocity) >= s.sanity_limits['angular-velocity']:
			s.sanity_limits_reached = True
			s.angular_velocity = 0

	def wind_momentum_angle(s) -> float:
		'''
		calculates the boat's momentum angle relative to the wind (absolute value)
		:return: 0 <= angle <= 180
		'''
		return abs(extras.diff_between_angles(s.global_wind.angle_degrees + 180, s.velocity.angle_degrees))

	def wind_angle(s) -> float:
		'''
		calculates the boat's angle relative to the wind
		:return: 0 <= angle <= 180
		'''
		return abs(extras.diff_between_angles(s.global_wind.angle_degrees + 180, 90))

	def rel_rudder_angle(s) -> float:
		'''
		:return: the current relative rudder angle (-90 to 90)
		'''
		return s.rudder.angle - 270

	def convert_vector_subclass(s, v, convert_to:str, unit_type:str='angle') -> Vec2d:
		'''
		wrapper for method of superclass convert_vector()
		'''
		return s.convert_vector(v=v, convert_to=convert_to, unit_type=unit_type, body_data=s.get_body_data())

	def geom_to_local_subclass(s, geom):
		'''
		wrapper for superclass method geom_to_local
		:param geom: shapely geometry object
		:return: same type as arg
		'''
		return s.geom_to_local(geom=geom, body_data=s.get_body_data())

	def local_velocity_subclass(s) -> Vec2d:
		'''
		wrapper for superclass method local_velocity()
		:return: vector
		'''
		return s.local_velocity(body_data=s.get_body_data())

	def get_body_data(s) -> dict:
		'''
		get body physics data
		:return: dict
		'''
		return {
			'angle': s.angle,
			'pos': s.pos,
			'velocity': s.velocity
		}

	def serializable(s) -> dict:
		'''
		creates a dictionary to save for the "boat" key in the simulation file or sent to a client
		:return: dict that can be JSON serialized
		'''
		return {
			'type': s.type_,
			'pos': list(s.pos),
			'velocity': list(s.velocity),
			'angle': s.angle,
			'angular-velocity': s.angular_velocity,
			'rudder-angle': s.rudder.angle,
			'hull-durability': s.hull_durability,
			'rudder-enable': s.rudder_enable,
			'sails': {sail_name: sail.serializable() for sail_name, sail in s.sails.items()},
			'forces': {name: [list(v) for v in f] for name, f in s.forces.items()}
		}


class Autopilot:
	'''
	autopilot emulator
	'''
	def __init__(s, boat:Sailboat, end_pos:Vec2d, max_rudder_movement:float, config:dict={}):
		'''
		init
		:param boat: boat object to control
		:param end_pos: end position, to set default target position
		:param max_rudder_movement: how fast the rudder can be moved in deg/sec
		:param config: config dict from a simulation file
		'''
		# save args
		s.boat = boat
		s.max_rudder_movement = max_rudder_movement
		# save config
		default_config = {'target-pos': ['global-pos', list(end_pos)], 'enabled': False}
		config = extras.validate_config_dict(d=config, default=default_config, types={key: type(value) for key, value in default_config.items()})
		s.get_global_target_pos(config['target-pos'])
		s.set_enabled_state(config['enabled'])

	def update(s, sim_t, user_input:dict) -> dict:
		'''
		updates the autopilot
		:param sim_t: simulation step time
		:param user_input: dict with input from the user (all keys are optional)
			enabled: whether the autopilot is enabled
			target-pos: target position
		:return: dict for the client
			on-course: whether the boat is "on course"
			tacking: whether the autopilot will have to tack to reach it's target position
			travel-time: estimated travel time
			target-pos: target position
		'''
		# save param
		s.sim_t = sim_t
		# validate user input
		extras.validate_config_dict(user_input, types={'enabled': bool, 'target-pos': list})
		# parse user input
		if 'enabled' in user_input.keys():
			s.set_enabled_state(user_input['enabled'])
		if 'target-pos' in user_input.keys():
			# TODO: validate target_pos_lst[1]
			s.get_global_target_pos(user_input['target-pos'])
		# get tack
		s.tach_wind_sign = extras.sign(s.boat.wind.x)# 1 for port tack, -1 for starboard tack
		# get target angle
		target_vector = s.get_global_target_pos() - s.boat.pos
		target_angle = target_vector.angle_degrees
		# get best tacking angle
		best_tacking_angle = ((s.boat.global_wind.angle_degrees + 180) - (s.boat.upwind_max_wind_angle * s.tach_wind_sign)) % 360
		# defaults
		angle = target_angle
		adj_leeway = False
		tacking = False
		try:
			travel_time = target_vector.length / s.boat.velocity.length
		except ZeroDivisionError:
			travel_time = None
		# decide weather to tack
		if abs(extras.diff_between_angles(s.boat.global_wind.angle_degrees + 180, target_angle)) < s.boat.upwind_max_total_leeway:
			angle = best_tacking_angle# the boat will have to tack
			try:
				travel_time = 0# TODO
			except ZeroDivisionError:
				travel_time = None
			if travel_time < 0:
				travel_time = None
			tacking = True
		# decide whether to compensate for leeway
		if abs(extras.diff_between_angles(s.boat.angle, angle)) < 45 and abs(extras.diff_between_angles(s.boat.velocity.angle_degrees, angle)) < 45 and s.boat.local_velocity_subclass().y > 0:
			adj_leeway = True
		else:
			travel_time = None
		# aim for angle
		s.aim_for_angle(angle, adj_leeway)
		return {'on-course': adj_leeway, 'tacking': tacking, 'travel-time': travel_time, 'target-pos': list(s.get_global_target_pos())}

	def get_global_target_pos(s, lst:list=None) -> Vec2d:
		'''
		gets/sets the current target position
		:param lst: target pos list, should only be given when the user has updated the target position
		:return: global pos Vec2d
		'''
		if lst is None:
			lst = s.target_pos_lst
		else:
			assert type(lst) == list and len(lst) == 2, 'autopilot target position must be a 2-item list'
			s.target_pos_lst = lst
			try:
				del s.relative_pos_original
			except Exception:
				pass
		type_, pos = lst
		assert type_ in ['global-pos', 'local-pos', 'user'], 'the 1st item in the list for the autopilot target pos should be "global-pos", "local-pos", or "user"'
		if type_ == 'global-pos':
			return Vec2d(*pos)
		if type_ == 'local-pos':
			if not hasattr(s, 'relative_pos_original'):
				s.relative_pos_original = s.boat.convert_vector_subclass(v=Vec2d(*pos), convert_to='global', unit_type='pos')
			return s.relative_pos_original
		if type_ == 'user':
			return s.get_user_pos_callback(pos)

	def aim_for_angle(s, angle:float, adj_leeway:bool=False) -> None:
		'''
		tries to aim the boat for angle `angle`
		:param angle: angle to aim for
		:param adj_leeway: whether to compensate for the boat's leeway
		:return: None
		'''
		if not s.enabled:
			return
		angle += s.boat.leeway_angle * s.tach_wind_sign * int(adj_leeway)
		angle %= 360
		offset_angle = extras.diff_between_angles(angle, s.boat.angle)
		rudder_angle = max(-60, min(60, offset_angle))
		if s.boat.local_velocity_subclass().y < 0:
			rudder_angle = -rudder_angle
		# check max rudder movement
		diff = extras.diff_between_angles(s.boat.rel_rudder_angle(), rudder_angle)
		s.boat.rudder_input_manager.set_input('autopilot', s.boat.rel_rudder_angle() + (extras.sign(diff) * min(abs(diff), s.max_rudder_movement * s.sim_t)))

	def set_enabled_state(s, state:bool) -> None:
		'''
		sets the enabled state
		:param state: enabled
		:return: None
		'''
		s.enabled = state
		if not s.enabled:
			s.boat.rudder_input_manager.disable_input('autopilot')

	def serializable(s) -> dict:
		'''
		creates a dict to save to a simulation file
		:return: JSON serializable dict
		'''
		return {'target-pos': s.target_pos_lst, 'enabled': s.enabled}


class WindGenerator:
	'''
	class to randomly generate somewhat realistic wind
	'''
	default_config = {'speed': 0, 'max-gust': 0, 'speed-variability': 0, 'direction-variability': 0, 'direction': 270}
	def __init__(s, config:dict):
		'''
		init
		:param config dictionary
		'''
		config = extras.validate_config_dict(d=config, default=WindGenerator.default_config)
		# assertions
		if False in [type(obj) in [float, int] for obj in config.values()]:
			raise ValueError('all wind generator settings must be of type int or float')
		# save args
		s.speed = config['speed']
		s.max_gust = config['max-gust']
		s.speed_variability = config['speed-variability']
		s.direction_variability = config['direction-variability']
		s.direction = config['direction']

	def get_vector(s, t:float) -> Vec2d:
		'''
		generates windspeed vector and updates simulation
		:param t: time (seconds) since last update
		:return: windspeed vector (meters/second)
		'''
		s.speed += (random.randint(int(-s.speed_variability * 100), int(s.speed_variability * 100)) / 100) * t
		s.speed = max(min(s.speed, s.max_gust), 0)
		s.direction += (random.randint(int(-s.direction_variability * 100), int(s.direction_variability * 100)) / 100) * t
		s.direction = s.direction % 360
		return Vec2d(s.speed, 0).rotated_degrees(s.direction)

	def serializable(s) -> dict:
		'''
		creates a dictionary to save for the "wind-settings" key in the simulation file
		:return: dict that can be JSON serialized
		'''
		return {
			'speed': s.speed,
			'max-gust': s.max_gust,
			'speed-variability': s.speed_variability,
			'direction-variability': s.direction_variability,
			'direction': s.direction
		}

	@staticmethod
	def new() -> dict:
		'''
		new default dict
		:return: new default dict
		'''
		return WindGenerator.default_config

	class GUI:
		'''
		handles GUI for wind settings
		'''
		def __init__(s, frame:tk.Frame, update_callback=None):
			'''
			creates GUI for wind settings
			:param frame: Tk frame
			:param update_callback: function to call when the settings are changed
			:return:
			'''
			# save params
			s.frame = frame
			s.update_callback = update_callback
			# create GUI
			slider_limits = {'speed': [0, 100, 0.1], 'max-gust': [0, 100, 0.1], 'speed-variability': [0, 10, 0.1], 'direction-variability': [0, 20, 1], 'direction': [0, 359, 1]}
			curr_row = 0
			# label
			tk.Label(s.frame, text='Wind').grid(row=curr_row, column=0, columnspan=2)
			# inputs
			curr_row += 1
			s.input_sliders = {}
			for key, l in slider_limits.items():
				# label
				tk.Label(s.frame, text=key.replace('-', ' ')).grid(row=curr_row, column=0)
				# slider
				s.input_sliders[key] = tk.Scale(s.frame, from_=l[0], to=l[1], resolution=l[2], orient=tk.HORIZONTAL)
				s.input_sliders[key].grid(row=curr_row, column=1)
				s.input_sliders[key].bind('<1>', (lambda scale: lambda _: scale.focus_set())(s.input_sliders[key]))# see stackoverflow.com/questions/2295290
				curr_row += 1

		def get(s) -> dict:
			'''
			gets config
			:return: dict
			'''
			return {key: float(widget.get()) for key, widget in s.input_sliders.items()}

		def update(s) -> None:
			'''
			calls s.update_callback when a slider is changed
			:return: None
			'''
			if type(s.update_callback) is not None:
				s.update_callback(s.get())


class SuperMap:
	'''
	map superclass for the simulation and rendering graphics
	'''
	def __init__(s, config: dict):
		'''
		init
		:param config: same format as a map file, see "resources" -> "map files" in documentation.html
		'''
		# constants
		s.required_config_keys = {'size': list, 'start': list, 'end': list, 'landmasses': list}
		# assertions / validations
		assert type(config) == dict, 'map config data must be of type dict'
		config = extras.validate_config_dict(d=config, required_keys=list(s.required_config_keys.keys()), types=s.required_config_keys)
		# create objects
		s.size = config['size']
		s.start = config['start']
		s.end = Vec2d(*config['end'])
		# create coastlines
		s.create_coastlines(config['landmasses'])

	def create_coastlines(s, lst:list) -> None:
		'''
		creates shapely coastline and representative points
		:param lst: list from map JSON data
		:return: None
		'''
		# save param
		s.landmasses = lst
		# default color
		default_color = extras.load_settings('GUI')['colors']['land']
		# change coords to poly objects
		for i, d in enumerate(s.landmasses):
			d['coords'] = Polygon(extras.compress_coords(d['coords']))
			d['rep-point'] = Point(d['rep-point'])
			# check that the corresponding representative point is inside the geom
			assert d['rep-point'].within(d['coords']), 'representative point must be inside corresponding landmass perimeter'
			# default color
			if 'color' not in d.keys():
				d['color'] = default_color
			s.landmasses[i] = d
		# assertions
		perimeters = [d['coords'] for d in s.landmasses]
		# make sure they don't overlap
		for i0, c0 in enumerate(perimeters):
			for i1, c1 in enumerate(perimeters):
				if i0 == i1:
					continue# don't check a geom against itself
				assert not (True in [c0.overlaps(c1), c0.within(c1), c1.overlaps(c0), c1.within(c0)]), 'coastline perimeters must not overlap or contain each other'

	def serializable(s) -> dict:
		'''
		:return: a serializable representation of this map (equivalent to data from map file)
		'''
		serializable_coastlines = []
		for d in s.landmasses:
			new_d = {}
			new_d['coords'] = list(d['coords'].exterior.coords)
			new_d['rep-point'] = list(d['rep-point'].coords[0])
			serializable_coastlines.append({**d, **new_d})
		return {
			'size': s.size,
			'start': s.start,
			'end': list(s.end),
			'landmasses': serializable_coastlines
		}

	def list_coastlines(s) -> list:
		'''
		creates a list of coastlines
		:return: list of coastline polygons
		'''
		return [landmass['coords'] for landmass in s.landmasses]

	def coastlines_rep_points(s) -> zip:
		'''
		:return: a list of tuples containing coastline polygons and corresponding representative points
		'''
		return zip(s.list_coastlines(), [coastline['rep-point'] for coastline in s.landmasses])

	def depth(s, pos:Vec2d) -> float:
		'''
		gets the water depth at `pos`
		:param pos: position
		:return: depth
		'''
		# this is a placeholder for future proofing
		return int(s.is_point_on_water(pos)) * 100

	def is_point_on_water(s, pos:Vec2d) -> bool:
		'''
		determines if `pos` is on the water
		:param pos: position to check
		:return: if it's in the water
		'''
		pos = extras.convert_pos(pos=pos, type_=Point)
		for coastline in s.list_coastlines():
			if coastline.contains(pos):
				return False
		return True


class Map(SuperMap):
	'''
	class for the coastline data and coastline collision detection for a whole map
	'''
	def __init__(s, config:dict):
		'''
		init
		:param config: same format as a map file, see "resources" -> "map files" in documentation.html
		'''
		# init superclass
		super().__init__(config)

	def detect_collision(s, boat:Sailboat) -> bool:
		'''
		detects if `boat` has impacted a coastline
		:return: boolean representing whether the boat is currently touching any coastline
		'''
		# create local polygons (relative to boat)
		tmp_coastline_polys = [boat.geom_to_local_subclass(coastline) for coastline in s.list_coastlines()]
		# get polygon for boat perimeter
		for coastline in tmp_coastline_polys:
			if boat.shapely_perim.within(coastline) or boat.shapely_perim.overlaps(coastline):
				return True
			# check for object tunneling
			if boat.geom_to_local_subclass(LineString([tuple(pos) for pos in [boat.pos, boat.prev_pos]])).intersects(coastline):
				return True
		return False


class ClientHandler:
	'''
	class for handling a client
	'''
	def __init__(s, config:dict, contacts:list, map:Map, time_logger:extras.TimeLogger, settings:dict, globally_paused:bool):
		'''
		init
		:param config: client config dict from sim file, see "resources" -> "simulation files" in documentation.html
		:param contacts: see "resources" -> "contacts.json" in documentation.html
		:param map: map object for the current simulation
		:param time_logger: time logger object
		:param settings: simulation settings
		:param globally_paused: whether the whole simulation is paused
		'''
		# save params
		s.map = map
		s.time_logger = time_logger
		s.globally_paused = globally_paused
		# assertions
		assert type(config) == dict, 'client config data must be of type dict'
		# settings
		s.update_settings(settings)
		# simulation config requirements
		s.required_config_keys = ['username', 'finished', 'boat', 'boat-start', 'boat']
		# NOTE: these need to be set every time because values that are passed by reference may be overwritten
		s.default_config = {'timer': {'t': 0, 'running': True}, 'tracer-lst': [], 'record': None, 'autopilot': {'target-pos': list(s.map.end), 'enabled': True, 'paused': False}, 'blocked': False}# autopilot not included because the default is dependant on the map
		# validate config
		config = extras.validate_config_dict(config, s.default_config, s.required_config_keys)
		# create objects
		s.last_update_time = None
		s.client_alerts = []
		s.events = []
		s.client_events = []
		s.ip = None
		s.username = config['username']
		s.password = [d['password'] for d in contacts if d['username'] == s.username][0]
		s.paused = config['paused']
		s.blocked = config['blocked']
		s.finished = config['finished']
		s.tracer_lst = config['tracer-lst']
		s.enabled = config['enabled']
		s.record = config['record']
		s.default_user_input = {'autopilot': {}, 'boat': {}, 'reset': False}
		s.user_input = copy.deepcopy(s.default_user_input)
		# copy current boat config if necessary
		if 'boat-start' in config.keys():
			s.boat_start_config = config['boat-start']
		else:
			s.boat_start_config = config['boat']
		# boat
		s.boat = Sailboat(s.time_logger, config['boat'], s.settings, Vec2d(0, 0))# TODO: fix arbitrary constant
		# general setup
		s.setup(config['boat'])
		# autopilot
		s.autopilot = Autopilot(s.boat, s.map.end, s.settings['max-rudder-movement'], config['autopilot'])
		# boat start
		s.boat_start_config = config['boat-start']
		# timer
		s.timer = extras.Timer(config['timer'])

	def __repr__(s) -> str:
		'''
		repr
		:return: string
		'''
		return f'<ClientHandler for user "{s.username}" representing boat at pos: {str(s.boat.pos)}>'

	def setup(s, boat_config:dict) -> None:
		'''
		does stuff that is required for __init__ and reset
		:param boat_config: boat dynamic config
		:return: None
		'''
		# setup boat
		s.boat.setup_general(boat_config)
		# set flags and records
		s.tracer_lst = []

	def update_settings(s, d:dict) -> None:
		'''
		updates the simulator settings
		:param d: simulator settings
		:return: None
		'''
		s.settings = d
		s.tracer_resolution = d['tracer-resolution']
		s.client_timeout = d['client-timeout']
		s.sanity_limits = d['sanity-limits']
		try:
			s.autopilot.max_rudder_movement = d['max-rudder-movement']
		except AttributeError:
			pass

	def setup_client(s, ip:str) -> None:
		'''
		sets up a connection with a client
		:param ip: IPv4 address that client is connecting from
		:return: None
		'''
		# save param
		s.ip = ip
		# set attrs
		s.last_update_time = time.time()

	def update(s, sim_t:float, global_wind:Vec2d, user_input:dict, client_listening:bool) -> dict:
		'''
		updates this client's boat
		:param sim_t: simulation frame time
		:param global_wind: global wind vector
		:param user_input: dictionary (all keys are optional) for user input:
			boat: (see Sailboat.update.__doc__)
			autopilot: (see Autopilot.update.__doc__)
			paused: whether this client is paused
			reset: whether this client has reset their boat
		:param client_listening: whether this iteration has a connection to the client
		:return: dict:
			events (list of these possible strings):
				'shipwreck': the boat just ran out of hull durability
				'finished': the boat finished for the first time
				'reset': this boat has been reset since the previous iteration
			client-success: boolean representing whether there were no errors
			client-return (data to get sent back to the clients within render distance):
				boat: (see Sailboat.serializable.__doc__.return)
				autopilot: (see Autopilot.update.__doc__.return)
				general:
					paused: whether this client is paused
					finished: whether the boat has finished
					enabled: whether the boat is enabled
					record: completion time record
					timer: current timer value
					alerts: list of lists that can be used as args for extras.Alert.add()
					events: list of strings representing events that happened since the previous update from the client
						"reset": boat was reset
						"shipwreck": boat was shipwrecked
						"finished <time> <whether new record>": boat finished
						"collision <damage>": the boat was in a collision
		'''
		# save params
		s.sim_t = sim_t
		# init return data
		return_dict = {
			'client-return': {
				'general': {}
			}
		}
		error = None
		# only update user input if the client is connected
		if client_listening:
			s.last_update_time = time.time()
			# verify user update dict
			try:
				s.user_input = extras.validate_config_dict(user_input, default=copy.deepcopy(s.default_user_input), types={'boat': dict, 'autopilot': dict, 'paused': bool, 'reset': bool})
			except Exception as e:
				error = f'invalid client update data: {str(e)}'
			# clear user input if disabled
			if not s.enabled:
				s.user_input['autopilot'] = copy.copy({})
			# check if paused
			if 'paused' in s.user_input.keys():
				s.set_paused_state(s.user_input['paused'])
			# check if reset
			if s.user_input['reset']:
				s.reset()
				s.user_input['reset'] = False# don't reset every frame
		# update autopilot
		try:
			return_dict['client-return']['autopilot'] = s.autopilot.update(s.sim_t, s.user_input['autopilot'])
		except Exception:
			error = f'autopilot update error may have been the result of invalid client data: {traceback.format_exc()}'
		# update boat
		if s.enabled and not s.get_paused_state():
			try:
				s.boat.update(global_wind, s.sim_t, s.user_input['boat'])
			except Exception:
				error = f'boat update error may have been the result of invalid client data: {traceback.format_exc()}'
			# tracer list
			if s.tracer_resolution != None and (len(s.tracer_lst) == 0 or (Vec2d(*s.tracer_lst[-1]) - s.boat.pos).length >= s.tracer_resolution):
				s.tracer_lst.append(list(s.boat.pos))
		# collision detection
		if s.map.detect_collision(s.boat) and s.enabled:
			# damage
			s.damage(s.boat.velocity.length, s.boat.mass)
			if s.enabled:
				# bounce
				s.boat.velocity = -s.boat.velocity
				s.boat.angular_velocity = -s.boat.angular_velocity
		# check sanity limits
		if s.boat.sanity_limits_reached:
			s.client_alerts.append(['sanity limits reached', (255, 0, 0), 1, True])
		# check if boat has gotten to the end position
		if extras.convert_pos(s.boat.convert_vector_subclass(v=s.map.end, convert_to='local', unit_type='pos'), Point).within(s.boat.shapely_perim) and s.enabled:
			if not s.finished:# first time
				s.timer.stop()
				s.finished = True
				# check if it's a record
				new_record = s.record is None or s.timer.result() < s.record
				if new_record:
					s.record = s.timer.result()
				s.client_events.append(f'finished {str(s.timer)} {int(new_record)}')
				s.events.append('finished')
		# add data to return dict
		if error == None:# no errors
			return_dict['client-return'] = {
				**return_dict['client-return'],
				'boat': s.boat.serializable(),
				'general': {
					'paused': s.get_paused_state(),
					'finished': s.finished,
					'enabled': s.enabled,
					'record': s.record,
					'timer': s.timer.result(),
					'reset': False
				}
			}
			if client_listening:
				# only send alerts of the client is guaranteed to get them
				return_dict['client-return']['general']['alerts'] = s.client_alerts
				s.client_alerts = []
				# send list of events
				return_dict['client-return']['general']['events'] = s.client_events
				s.client_events = []
		else:# error
			return_dict['client-return'] = error
		return_dict['client-success'] = error is None
		return_dict['events'] = s.events
		s.events = []
		# return
		return return_dict

	def damage(s, speed:float, mass:float) -> None:
		'''
		handles taking damage
		:param speed: collision speed
		:param mass: collision mass
		:return: None
		'''
		if s.boat.max_hull_durability == -1 or s.boat.hull_durability == 0:
			return# boat is undamageable
		# calculate and apply damage
		damage = speed * mass * 0.01
		s.boat.hull_durability = max(s.boat.hull_durability - damage, 0)
		# add alert
		s.client_events.append(f'collision {damage}')
		# check if the boat's hull durability has run out
		if s.boat.hull_durability == 0:
			s.shipwreck()

	def add_alert(s, alert_lst:list) -> None:
		'''
		ads an alert
		:param alert_lst: list that can be used as args for extras.Alert.add
		:return: None
		'''
		assert 3 <= len(alert_lst) <= 4
		s.client_alerts.append(alert_lst)

	def set_blocked(s, blocked:bool) -> None:
		'''
		sets this user's blocked state
		:param blocked: whether this user is blocked
		:return: None
		'''
		assert type(blocked) == bool, '1st arg `blocked` must be boolean'
		s.blocked = blocked

	def get_paused_state(s) -> bool:
		'''
		gets the paused state
		:return: whether this client handler is paused
		'''
		return s.paused or s.globally_paused

	def set_paused_state(s, paused:bool, type_:str='local') -> None:
		'''
		sets the paused state
		:param paused: paused state
		:param type_: can be 'local' or 'global'
		:return: None
		'''
		assert type_ in ['local', 'global']
		if type_ == 'local':
			s.paused = paused
		else:
			s.globally_paused = paused
		if s.get_paused_state():
			s.timer.stop()
		else:
			if s.enabled and not s.finished:
				s.timer.start()

	def shipwreck(s) -> None:
		'''
		changes the state if the sim and the GUI to disable the user's control of the boat
		:return: None
		'''
		s.timer.stop()
		s.events.append('shipwreck')
		s.client_events.append('shipwreck')
		s.boat.velocity = Vec2d(0, 0)
		s.boat.angular_velocity = 0
		s.boat.forces = copy.deepcopy(Sailboat.default_forces)
		s.autopilot.set_enabled_state(False)
		if not s.enabled:
			return# this has already run
		s.enabled = False

	def serializable(s, type_:str) -> dict:
		'''
		:param type_: what this is for, can be 'file', 'client', or 'minimal'
		:return: JSON serializable dict to write to a simulation file, sent to a joining client, or viewed by the admin
		'''
		assert type_ in ['file', 'client', 'minimal', 'status-admin-view'], 'type_ must be "file", "client", "minimal", or "status-admin-view"'
		if type_ == 'minimal':
			return {
				'general': {
					'enabled': s.enabled,
					'paused': s.get_paused_state()
				},
				'boat': {
					'pos': list(s.boat.pos),
					'angle': s.boat.angle,
					'velocity': list(s.boat.velocity)
				}
			}
		if type_ == 'status-admin-view':
			if not (s.last_update_time is None):
				online = time.time() - s.last_update_time < s.client_timeout
			else:
				online = False
			return {
				'online': online,
				'ip': s.ip,
				'password': s.password,
				'paused': s.get_paused_state(),
				'blocked': s.blocked
			}
		return_dict = {
			'username': s.username,
			'finished': s.finished,
			'paused': s.get_paused_state(),
			'blocked': s.blocked,
			'enabled': s.enabled,
			'record': s.record,
			'tracer-lst': s.tracer_lst,
			'timer': s.timer.serializable(),
			'autopilot': s.autopilot.serializable(),
			'boat-start': s.boat_start_config,
			'boat': s.boat.serializable()
		}
		if type_ == 'client':
			return_dict = {
				**return_dict,
				'boat-static-config': s.boat.static_config
			}
		return return_dict

	def reset(s) -> None:
		'''
		resets this user
		:return: None
		'''
		s.setup(s.boat_start_config)
		s.finished = False
		s.enabled = True
		s.paused = False
		s.events.append('reset')
		s.client_events.append('reset')
		s.timer.reset()
		if not s.get_paused_state():
			s.timer.start()

	@staticmethod
	def new(boat:str, map:str, username:str='__admin__') -> dict:
		'''
		:param boat: boat type filename
		:param map: map filename
		:param username: username
		:return: client dict for a new simulation
		'''
		boat_config = Sailboat.get_new_dict(boat, map)
		return {
			'username': username,
			'finished': False,
			'paused': False,
			'enabled': True,
			'tracer-lst': [],
			'timer': extras.Timer({'running': True}).serializable(),
			'autopilot': {
				'enabled': False
			},
			'boat-start': boat_config,
			'boat': boat_config
		}


class Simulator:
	'''
	global physics simulator class
	'''
	auth_failed_msg = 'Either you have invalid credentials or have been blocked'
	def __init__(s, sim_name:str, admin_code:int, parse_admin_command_callback:callable):
		'''
		NOTE: all "global" angles are in degrees anticlockwise, 0=east
		NOTE: all "global" coordinates are in meters from the bottom-left corner of the map being used
		NOTE: all speeds/velocities are in meters/sec
		NOTE: all times are in seconds
		NOTE: all forces are in kilograms
		NOTE: all torques are in meter-kilograms anticlockwise
		NOTE: all wind vectors represent the direction that the wind is moving, not coming from
		:param sim_name: filename (without extension) of simulation in the `simulations` folder
		:param admin_code: unsigned integer used as a password for __admin__
		:param parse_admin_command_callback: reference to ProcManager.parse_admin_command()
		'''
		# save params
		s.sim_name = sim_name
		s.admin_code = admin_code
		s.parse_admin_command_callback = parse_admin_command_callback
		# settings
		s.load_settings()
		# flag and record defaults
		s.time_logger = extras.TimeLogger()
		s.time_logger_results = ''
		s.errors = []
		s.fps = 0# frames per second
		s.time_logger = extras.TimeLogger()
		s.send_client_states_to_admin = False
		# load contacts
		s.load_contacts()
		# load list of resources
		s.load_lists()
		# placeholder wind vector
		s.wind_vector = Vec2d(0, 0)
		# load simulation data
		sim_config = s.load_sim_file(sim_name)
		s.record = sim_config['record']
		s.map_name = sim_config['map']
		wind_config = sim_config['wind-settings']
		s.paused = sim_config['paused']
		s.password = sim_config['password']
		# load map
		os.chdir(extras.resources.maps_dir)
		with open(s.map_name + '.json') as f:
			map_config = json.loads(f.read())
		s.map = Map(map_config)
		# load client objects
		s.client_handlers = {username: ClientHandler(config, s.contacts, s.map, s.time_logger, s.settings, s.paused) for username, config in sim_config['clients'].items()}
		# give all autopilots a callback function to get the position of any user's boat
		for _, client_handler in s.client_handlers.items():
			client_handler.autopilot.get_user_pos_callback = s.get_user_pos
		# init wind generator object
		s.wind_generator = WindGenerator(config=wind_config)
		# timing
		s.fps_tracker = extras.FPSSmoother()
		s.timer = extras.Timer(sim_config['timer'])

	def __repr__(s) -> str:
		'''
		repr
		:return: string
		'''
		return f'<Simulator simulation="{s.sim_name}">'

	def load_contacts(s) -> None:
		'''
		loads client authentication info from contacts.json
		:return: None
		'''
		os.chdir(extras.resources.base_dir)
		with open('contacts.json') as f:
			s.contacts = json.loads(f.read())
		# __admin__ special case
		for i, contact in enumerate(s.contacts):
			if contact['username'] == '__admin__':
				s.contacts[i]['password'] = str(s.admin_code)
				return
		s.contacts.append({'username': '__admin__', 'password': str(s.admin_code)})

	def load_lists(s) -> None:
		'''
		loads the sim, boat, and map lists
		:return: None
		'''
		s.sim_lst = [name.split('.')[0] for name in os.listdir(extras.resources.simulations_dir) if name.lower() != '.ds_store']
		s.boat_lst = [name.split('.')[0] for name in os.listdir(extras.resources.boat_dir) if name.lower() != '.ds_store']
		s.map_lst = [name.split('.')[0] for name in os.listdir(extras.resources.maps_dir) if name.lower() != '.ds_store']

	def load_settings(s) -> None:
		'''
		loads settings from settings.json, current simulation file, or s.settings_d.
		:return: None
		'''
		d = extras.load_settings('simulator', s.sim_name)
		s.save_sims = d['save-sims']
		s.lag_limit = d['lag-limit']
		s.settings = d
		# update clients
		try:
			[client.update_settings(d) for client in s.client_handlers]
		except AttributeError:
			pass

	def load_sim_file(s, sim_name:str) -> dict:
		'''
		loads a simulation file
		:param sim_name: simulation file name
		:return: sim data
		'''
		# simulation config requirements
		s.required_sim_config_keys = ['map', 'wind-settings', 'clients']
		# NOTE: these need to be set every time because values that are passed by reference may be overwritten
		s.default_sim_config = {'timer': extras.Timer().serializable(), 'record': -1, 'paused': False, 'password': None}# autopilot not included because the default is dependant on the map
		os.chdir(extras.resources.simulations_dir)
		with open(sim_name + '.json') as f:
			sim_config = json.loads(f.read())
		return extras.validate_config_dict(sim_config, s.default_sim_config, s.required_sim_config_keys)

	def client_connect(s, auth:list, ip:str) -> list:
		'''
		checks if a client can connect
		:param auth: authentication list
		:param ip: client IPv4 address
		:return: list:
			* bool representing whether the client authentication succeeded
			* dict to init the client from s.serializable('client') or error message
		'''
		# get username, password, and sim password
		username, password, sim_password = auth
		# authenticate client
		if not s.authenticate_client(username, password, sim_password):
			return [False, Simulator.auth_failed_msg]
		# start dict for all clients
		s.client_handlers[username].setup_client(ip)
		return [True, s.serializable('client' + ('-admin' * int(username == '__admin__')))]

	def update(s, user_input) -> list:
		'''
		updates everything in the simulation
		:param user_input: list of dicts from each client of the following format:
			auth: list
				* client username
				* client password
				* simulation password
			user-input: see ClientHandler.update.__doc__
			render-dist: maximum distance that the user can see other boats
			render-dist-extra-boats: (only for the user __admin__, otherwise ignored)(optional) list of usernames to include in the render distance results regardless of distance
			admin-commands: (only for the user __admin__, otherwise ignored)(optional) list of lists to be passed to ProcManager.parse_admin_command()
		:return: list of lists of the following format, corresponding to `user_input`:
			* (bool): False if there was any kind of error
			* error message or dictionary to be returned to the client as JSON:
				global-data:
					paused: whether the whole simulation is paused
					wind: 2D list for global wind vector
					FPS: server framerate
					timer: global simulation timer current value
					client-states: only for __admin__, dict included when the admin send the STATUS command:
						<username>: dictionary for client that can only be viewed by __admin__, see ClientHandler.serializable('status-admin-view')
				clients: dictionary for each boat within this client's render distance
					<username>: dictionary for client's boat, see ClientHandler.update.__doc__.return.client-return
		'''
		try:
			s.time_logger.stop_log('tkinter loop')
		except Exception:# if it's the first iteration this won't work
			pass
		frame_t_micros = s.fps_tracker.record()
		s.fps = 1_000_000 / max(frame_t_micros, 1)
		s.fps_mean = s.fps_tracker.get()
		frame_t = frame_t_micros / 1_000_000
		# check if not to run sim
		if s.paused:
			sim_t = 0
		else:
			if frame_t > s.lag_limit:# don't allow lag to jump the simulation by unrealistic intervals
				frame_t = s.lag_limit
			# get sim time
			sim_t = frame_t * s.timer.ratio
		# generate new wind vector
		s.wind_vector = s.wind_generator.get_vector(sim_t)
		# user return
		user_returns = {}# dict of: {(int): corresponding index of user_input, return data or error message}
		client_handler_input = {}
		client_handler_data = {}
		# lop through client data
		for i, client_dict in enumerate(user_input):
			# validate data
			try:
				assert type(client_dict) == dict, 'client update request data must be of type dict'
				client_dict = extras.validate_config_dict(client_dict, default={'user-input': {}}, required_keys=['auth', 'render-dist'], types={'auth': list, 'user-input': dict, 'render-dist': float})
			except AssertionError as e:
				user_returns[i] = [False, f'client update request format error: {str(e)}']
				continue
			# authenticate client
			if not s.authenticate_client(*client_dict['auth']):
				user_returns[i] = [False, Simulator.auth_failed_msg]
				continue
			# client handler input
			client_handler_input[client_dict['auth'][0]] = client_dict['user-input']
			# admin commands
			if client_dict['auth'][0] == '__admin__':
				try:
					if 'admin-commands' in client_dict.keys():
						for cmmd_lst in client_dict['admin-commands']:
							s.parse_admin_command_callback(cmmd_lst)
				except Exception as e:
					user_returns[i] = [False, f'Exception caused by the "admin-commands" key: {str(e)}']
				if 'render-dist-extra-boats' in client_dict.keys():
					admin_render_dist_include_boats = client_dict['render-dist-extra-boats']
				else:
					admin_render_dist_include_boats = []
		# loop through client handlers
		s.time_logger.start_log('client handlers')
		for username, client_handler in s.client_handlers.items():
			# get client update data
			if username in client_handler_input.keys():
				curr_user_input = client_handler_input[username]
				client_listening = True
			else:
				curr_user_input = {}
				client_listening = False
			# update handler
			s.time_logger.start_log(username)
			client_handler_return = client_handler.update(sim_t, s.wind_vector, curr_user_input, client_listening)
			# check for error
			if not client_handler_return['client-success']:
				i = None
				for i, d in enumerate(user_input):
					if d['auth'][0] == username:
						break
				assert type(i) == int, f'could not find user input for user "{username}", however the client handler failed with this message: {client_handler_return["client-return"]}'
				user_returns[i] = [False, client_handler_return['client-return']]
			client_handler_data[username] = client_handler_return['client-return']
			s.time_logger.stop_log(username)
			# go through list of events
			for event in client_handler_return['events']:
				if event == 'shipwreck':
					s.add_global_alert([f'user {username} shipwrecked', (255, 0, 0), 5, True])
				if event == 'finished':
					s.add_global_alert([f'user {username} finished with a time of {str(client_handler.timer)}', (0, 255, 0), 5, True])
				if event == 'reset':
					s.add_global_alert([f'user {username} reset', (0, 255, 0), 5, True])
		s.time_logger.stop_log('client handlers')
		# detect collisions between boats
		s.detect_boat_collisions()
		# loop through client data again to put data in user_return
		for i, client_dict in enumerate([client_dict for i, client_dict in enumerate(user_input) if i not in user_returns.keys()]):
			admin = user_input[i]['auth'][0] == '__admin__'
			render_dist_users = s.users_in_render_dist(client_dict['render-dist'], s.client_handlers[client_dict['auth'][0]].boat.pos)
			if admin:
				render_dist_users = list({*render_dist_users, *admin_render_dist_include_boats})# sets cannot contain duplicate items
			user_returns[i] = [
				True,
				{
					'global-data': {
						'paused': s.paused,
						'wind': list(s.wind_vector),
						'FPS': s.fps_mean,
						'timer': s.timer.result()
					},
					'clients': {username: [s.client_handlers[username].serializable('minimal'), client_handler_data[username]][int(username in render_dist_users)] for username in s.client_handlers.keys()}
				}
			]
			if admin:
				if s.send_client_states_to_admin:
					user_returns[i][1]['global-data']['client-states'] = {name: client_handler.serializable('status-admin-view') for name, client_handler in s.client_handlers.items()}
					s.send_client_states_to_admin = False
		return [d for _, d in sorted(user_returns.items(), key=lambda t:t[0])]

	def add_global_alert(s, lst:list) -> None:
		'''
		adds global alert
		:param lst: see ClientHandler.add_alert.__doc__
		:return: None
		'''
		[client_handler.add_alert(lst) for _, client_handler in s.client_handlers.items()]

	def authenticate_client(s, username:str, psswd:str, sim_psswd:str=None) -> bool:
		'''
		authenticates client
		:param username: username
		:param psswd: password
		:param sim_psswd: optional simulation password
		:return: whether username and password are correct
		'''
		# check simulation password
		if s.password is not None and sim_psswd is not None and s.password != sim_psswd:
			return False
		# check client username and password
		for curr_username, client in s.client_handlers.items():
			if curr_username == username and client.password == psswd:
				# check if account is blocked
				if s.client_handlers[username].blocked:
					return False
				return True
		return False

	def users_in_render_dist(s, radius:float, pos:Vec2d) -> list:
		'''
		lists all boats that are within the render distance of a certain client
		:param radius: client's render distance
		:param pos: global position
		:return: list of usernames of boats within render distance
		'''
		return [username for username, client in s.client_handlers.items() if (client.boat.pos - pos).length - client.boat.perim_max_radius < radius]

	def detect_boat_collisions(s) -> None:
		'''
		detects and handles boat collisions
		:return: None
		'''
		client_handlers = list(s.client_handlers.items())
		for i0, item_tuple0 in enumerate(client_handlers):
			for i1, item_tuple1 in enumerate(client_handlers):
				if i0 >= i1:
					continue# don't double-check any two client handlers
				users = [item_tuple0[1], item_tuple1[1]]
				if not (True in [user.enabled for user in users]):
					continue# if both boats are shipwrecked, ignore collision
				global_hulls = [Polygon([extras.convert_pos(user.boat.convert_vector_subclass(v=pos, convert_to='global', unit_type='pos'), list) for pos in user.boat.shapely_perim.exterior.coords]) for user in users]
				# test if hulls are touching
				if global_hulls[0].touches(global_hulls[1]) or global_hulls[0].overlaps(global_hulls[1]) or global_hulls[1].overlaps(global_hulls[0]) or global_hulls[0].within(global_hulls[1]) or global_hulls[1].within(global_hulls[0]):
					# calculate damage, both boats will take the same damage if damageable
					speed = (users[0].boat.velocity - users[1].boat.velocity).length
					mass = min([users[0].boat.mass, users[1].boat.mass])
					[user.damage(speed=speed, mass=mass) for user in users]
					s.add_global_alert([f'{item_tuple0[0]} collided with {item_tuple1[0]}', (255, 0, 0), 5, True])
					# bounce (boats will trade translational and angular velocities)
					if not (False in [user.enabled for user in users]):# if both boats are enabled
						tmp_trans, tmp_ang = users[0].boat.velocity, users[0].boat.angular_velocity
						if users[0].enabled:
							users[0].boat.velocity, users[0].boat.angular_velocity = users[1].boat.velocity, users[1].boat.angular_velocity
						if users[1].enabled:
							users[1].boat.velocity, users[1].boat.angular_velocity = tmp_trans, tmp_ang
					else:# one boat enabled, other shipwrecked
						tmp_boat = users[int(users[1].enabled)].boat
						# bounce
						tmp_boat.velocity = -tmp_boat.velocity
						tmp_boat.angular_velocity = -tmp_boat.angular_velocity

	def set_time_ratio(s, ratio:float) -> None:
		'''
		sets the simulation time ratio
		:param ratio: time ratio
		:return: None
		'''
		assert type(ratio) in [float, int]
		s.timer.set_ratio(ratio)
		[client_handler.timer.set_ratio(ratio) for _, client_handler in s.client_handlers.items()]

	def get_user_pos(s, username:str) -> None:
		'''
		used as a callback for the autopilot objects in the client handlers to track other users
		:param username: username
		:return: position of username's boat
		'''
		return s.client_handlers[username].boat.pos

	def toggle_paused_state(s) -> None:
		'''
		toggles the paused state
		:return: None
		'''
		s.paused = not s.paused
		[client.set_paused_state(s.paused, type_='global') for _, client in s.client_handlers.items()]
		if s.paused:
			s.add_global_alert(['simulation paused', (0, 255, 0), 5])
			s.timer.stop()
		else:
			s.add_global_alert(['simulation unpaused', (0, 255, 0), 5])
			s.timer.start()

	def serializable(s, type_:str) -> dict:
		'''
		creates config dict to bre saved or sent to each client
		:param type_: what this is for, can be 'file', 'client', or 'client-admin'
		:return: JSON serializable dictionary, see "resources" -> "map files" in the documentation or a dict to be sent to a joining client
		'''
		assert type_ in ['file', 'client', 'client-admin', 'http-response']
		client_serialization_types = {'file': 'file', 'client': 'client', 'client-admin': 'client', 'http-response': 'minimal'}
		clients = {username: client_handler.serializable(client_serialization_types[type_]) for username, client_handler in s.client_handlers.items()}
		return_dict = {
			'paused': s.paused,
			'record': s.record,
			'clients': clients,
			'timer': s.timer.serializable()
		}
		if type_ == 'file':
			return_dict = {
				**return_dict,
				'map': s.map_name,
				'password': s.password,
				'wind-settings': s.wind_generator.serializable()
			}
		if type_.startswith('client'):
			return_dict = {
				**return_dict,
				'map': s.map.serializable(),
				'server-software-version': extras.version_tuple
			}
		if type_ == 'client-admin':
			return_dict = {
				**return_dict,
				'boats-static-config': {client_handler.boat.type_: client_handler.boat.static_config for _, client_handler in s.client_handlers.items()}
			}
		if type_ == 'http-response':
			return_dict['server-software-version'] = extras.version_tuple
		return return_dict

	def save(s) -> list:
		'''
		saves the simulation
		:return: [(bool): whether there have been no problems, error message or None]
		'''
		if s.save_sims:
			os.chdir(extras.resources.simulations_dir)
			rtrn = extras.update_json_file(os.path.join(extras.resources.simulations_dir, s.sim_name) + '.json', s.serializable('file'), write_if_invalid=True)
			if not rtrn[0]:
				return rtrn
		return [True, None]

	def reset(s) -> None:
		'''
		resets the simulation
		:return: None
		'''
		s.paused = False
		# reset clients
		[client.set_paused_state(s.paused, type_='global') for _, client in s.client_handlers.items()]
		[client.reset() for _, client in s.client_handlers.items()]
		# reset timer
		s.timer.reset()
		s.timer.set_ratio(1)
		s.timer.start()
		# add alert
		s.add_global_alert(['simulation reset', (0, 255, 0, 0), 5, False])

	@staticmethod
	def new_sim(boat:str, map:str, name:str, wind_settings:dict, password:str=None) -> list:
		'''
		creates a new simulation file
		:param boat: boat name
		:param map: map name
		:param name: simulation name
		:param wind_settings: dict representing the wind settings chosen by the user
		:param password: optional simulation password
		:return: [(bool): whether there have been no problems, error message or None]
		'''
		d = {
			'map': map,
			'paused': False,
			'clients': {'__admin__': ClientHandler.new(boat, map)},
			'wind-settings': wind_settings,
			'timer': extras.Timer({'running': True}).serializable()
		}
		if password != '':
			d['password'] = password
		# validate name
		name = extras.validate_filename(name)
		# check if sim doesn't already exist
		if name.lower() + '.json' in [fn.lower() for fn in os.listdir(extras.resources.simulations_dir)]:
			return [False, f'simulation name "{name}" already exists']
		# create file
		os.chdir(extras.resources.simulations_dir)
		with open(name + '.json', 'w') as f:
			f.write(json.dumps(d))
		return [True, None]


class ProcManager:
	'''
	manages this server process
	'''
	def __init__(s, send_queue:mp.Queue, admin_code:int, sim_name:str, port:int, public:bool):
		'''
		init
		:param send_queue: queue to watch
		:param admin_code: 32-bit integer as string to use for the password for __admin__
		:param sim_name: simulation name
		:param port: port number to use for server
		:param public: whether this server is public or private
		'''
		# save params
		s.send_queue = send_queue
		s.admin_code = admin_code
		s.port = port
		s.public = public
		# blocked list
		s.blocked_IPs = []
		# attempt to load simulator
		extras.dbp(f'ProcManager.__init__: initiating simulator, sim name is {sim_name}')
		s.sim = Simulator(sim_name, s.admin_code, s.parse_admin_command)
		# flags
		s.running = True
		s.waiting_connections = []
		s.waiting_connections_lock = False
		# get IP address
		if s.public:
			s.ip = socket.gethostbyname(socket.gethostname())
		else:
			s.ip = '127.0.0.1'# loopback interface
		# start listening on port
		extras.dbp(f'ProcManager.__init__: starting server socket, ip={s.ip}, port={str(s.port)}')
		s.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		s.server_socket.bind((s.ip, s.port))

	def __repr__(s) -> str:
		'''
		repr
		:return: string
		'''
		return f'<ProcManager simulator={repr(s.sim)}, ip={s.ip}, port={str(s.port)}>'

	def main_loop(s) -> None:
		'''
		this method is called in a different process
		:return: None
		'''
		extras.dbp(f'ProcManager.main_loop: listening on port {str(s.port)}')
		s.server_socket.listen()
		extras.dbp('ProcManager.main_loop: starting loop')
		s.accept_thread = threading.Thread(target=s.connection_accept_loop)
		s.accept_thread.start()
		s.send_queue.put('START')
		while s.running:
			# step 1: get requests from server socket
			s.waiting_connections_lock = True
			connections = s.waiting_connections[:len(s.sim.client_handlers)]
			del s.waiting_connections[:len(s.sim.client_handlers)]
			s.waiting_connections_lock = False
			# step 2: validate and run commands that don't require the sim to be updated
			client_updates = {}# dict of connection indices and client update dicts, see Simulator.update.__doc__
			for i, t in enumerate(connections):
				conn, addr = t
				valid, error, if_update, data, http = s.parse_client_data(conn.recv(1024), addr[0])
				if not valid:
					s.send(conn, [False, error])
					continue
				if if_update:
					client_updates[i] = data
					continue
				if http:
					conn.sendall(s.http_response(data))# TODO: FIX: ConnectionAbortedError: [WinError 10053] An established connection was aborted by the software in your host machine
					conn.close()
					continue
				s.send(conn, [True, data])
			# step 3: update simulator
			client_update_returns = s.sim.update([d for _, d in sorted([t for t in client_updates.items()], key=lambda t:t[0])])
			# step 4: respond to connections that required sim update information
			for conn_index, client_return in zip(sorted(client_updates.keys()), client_update_returns):
				s.send(connections[conn_index][0], client_return)
		extras.dbp('ProcManager.main_loop: ending loop')
		s.server_socket.close()

	def send(s, conn:socket.socket, data, include_header:bool=True) -> None:
		'''
		sends `data` on `conn`
		:param conn: socket connection object
		:param data: return data
		:param include_header: whether to use the size header
		:return: None
		'''
		original_str = json.dumps(data)
		if include_header:
			conn.sendall(extras.to_bytes(f'{str(len(original_str))} {original_str}'))
		else:
			conn.sendall(extras.to_bytes(original_str))

	def parse_admin_command(s, lst:list) -> None:
		'''
		NOTE: data sent to this function is trustworthy
		control commands:
			BLOCK: blocks given IP address
			UNBLOCK: unblocks given IP address
			QUIT: quits the server
			RELOAD-SETTINGS: reloads the simulator settings
			SET-TIME-CONST: sets the time constant
			RESET: resets the simulation
			TOGGLE-PAUSE: toggles whether the simulation is globally paused
			STATUS: returns status info about all the users
			USER-RESET: next parameter should be the username to reset
			USER-TOGGLE-PAUSE: next parameter should be the username to toggle the local pause state
			USER-SET-POS: requires 2 params: user and pos list, sets position of boat
			USER-REPAIR: repairs given user's boat durability
			USER-BLOCK: blocks user
			USER-UNBLOCK: unblocks user
		:param lst: list of commands
		'''
		assert type(lst) == list, 'admin control command must be of type list'
		assert lst[0].lower() in ['block', 'unblock', 'quit', 'reload-settings', 'set-time-const', 'reset', 'toggle-pause', 'status', 'user-reset', 'user-toggle-pause', 'user-set-pos', 'user-repair', 'user-block', 'user-unblock'], f'first item in admin command list "{str(lst[0])}" is not recognized (see list in this assert statement)'
		try:
			if lst[0] == 'BLOCK':
				if lst[1] not in s.blocked_IPs:
					s.blocked_IPs.append(lst[1])
			if lst[0] == 'UNBLOCK':
				try:
					s.blocked_IPs.remove(lst[1])
				except Exception:
					pass
			if lst[0] == 'QUIT':
				s.quit()
			if lst[0] == 'RELOAD-SETTINGS':
				s.sim.load_settings()
			if lst[0] == 'SET-TIME-CONST':
				s.sim.set_time_ratio(lst[1])
			if lst[0] == 'RESET':
				s.sim.reset()
			if lst[0] == 'TOGGLE-PAUSE':
				s.sim.toggle_paused_state()
			if lst[0] == 'STATUS':
				s.sim.send_client_states_to_admin = True
			if lst[0] == 'USER-RESET':
				try:
					s.sim.client_handlers[lst[1]].reset()
				except Exception:
					pass
			if lst[0] == 'USER-TOGGLE-PAUSE':
				try:
					client_handler = s.sim.client_handlers[lst[1]]
					client_handler.set_paused_state(not client_handler.paused, type_='local')
				except Exception:
					pass
			if lst[0] == 'USER-SET-POS':
				try:
					s.sim.client_handlers[lst[1]].boat.pos = Vec2d(*lst[2])
				except Exception:
					pass
			if lst[0] == 'USER-REPAIR':
				try:
					user = s.sim.client_handlers[lst[1]]
					if not user.enabled:
						return
					boat = user.boat
					boat.hull_durability = boat.max_hull_durability
					user.add_alert(['Boat durability fixed by Admin', (0, 255, 0), 5, True])
				except Exception:
					pass
			if lst[0] == 'USER-BLOCK':
				try:
					s.sim.client_handlers[lst[1]].set_blocked(True)
				except KeyError:
					extras.dbp(f'ProcManager.parse_admin_command: admin tried to block user {lst[1]} which does not exist')
			if lst[0] == 'USER-UNBLOCK':
				try:
					s.sim.client_handlers[lst[1]].set_blocked(False)
				except KeyError:
					extras.dbp(f'ProcManager.parse_admin_command: admin tried to unblock user {lst[1]} which does not exist')
		except Exception as e:
			raise type(e)(f'Error while parsing admin commands with command list: {str(lst)}, the error was: {str(e)}')

	def parse_client_data(s, bytes_data:bytes, ip:str) -> tuple:
		'''
		:param bytes_data: bytes object from client, client JSON commands are always lists with the first item being one of the following:
			JOIN:
				this should always be the first command sent by a client, should be a dict of the following format:
					auth (list):
						* client username
						* client password
						* simulation password
				:returns: (see Simulator.client_connect.__doc__.return)
			UPDATE: see Simulator.update.__doc__
				:returns: see Simulator.update.__doc__.return
		:param ip: incoming IP address
		:return: tuple:
			* whether the client data was successfully parsed and their IP isn't blocked
			* error message or None
			* whether this request requires a simulation update
			* update data for the simulation, client return data, or None
			* whether to respond with the HTML page
		'''
		# assertion
		assert extras.validate_ipv4(ip), '2nd arg `ip` must be a valid IPv4 address'
		# check if IP is blocked
		if ip in s.blocked_IPs:
			return False, 'Your IP address has been blocked from this server', False, None, False
		# attempt to decode as ASCII
		try:
			ascii_data = bytes_data.decode('ascii')
		except UnicodeDecodeError as e:
			return False, 'client error: could not decode binary as ASCII: ' + str(e), False, None, False
		# check if HTTP request, very crude, not currently working
		if len(ascii_data) >= 3 and ascii_data[:3] == 'GET':
			return True, None, False, ascii_data, True
		# attempt to decode as JSON
		try:
			client_data = json.loads(ascii_data)
		except json.JSONDecodeError as e:
			return False, 'client error: could not decode binary as JSON: ' + str(e), False, None, False
		# assertions
		if type(client_data) != list:
			return False, 'invalid sending data structure type, must be list', False, None, False
		if len(client_data) == 0:
			return False, 'request command list must not be of length 0', False, None, False
		if type(client_data[0]) != str:
			return False, 'first arg in command list must be of type string', False, None, False
		# use first arg (command)
		command = client_data[0]
		if command not in ['JOIN', 'UPDATE']:
			return False, 'first arg in request is invalid, it must be "JOIN" or "UPDATE"', False, None, False
		try:
			if command == 'JOIN':
				rtrn = s.sim.client_connect(client_data[1]['auth'], ip)
				if rtrn[0]:
					return True, None, False, rtrn[1], False
				else:
					return False, rtrn[1], False, None, False
			if command == 'UPDATE':
				return True, None, True, client_data[1], False
		except Exception:
			return False, f'client request format error caused the following exception:\n{traceback.format_exc()}', False, None, False

	def connection_accept_loop(s) -> None:
		'''
		this is meant to run in a separate thread and accept connections
		:return: None
		'''
		while s.running:
			if not s.waiting_connections_lock:
				try:
					s.waiting_connections.append(s.server_socket.accept())
				except Exception as e:
					s.quit()
					print(f'error in connection accept loop: {str(e)}')

	def http_response(s, request:str) -> bytes:
		'''
		serves a simple webpage for HTTP requests
		:param request: decoded request
		:return: response
		'''
		ver = '.'.join(extras.version_tuple)
		success, dir_ = extras.HTTP_GET_validate(req=request)
		if success:
			dirs = ['/', '/page_data_updater.js', '/data.json', '/favicon.ico']
			if dir_ in dirs:
				if dir_ == '/':
					os.chdir(extras.http_dir)
					with open('index.html', 'rb') as f:
						body = f.read()
					content_type = 'text/html'
				if dir_ == '/page_data_updater.js':
					os.chdir(extras.http_dir)
					with open('page_data_updater.js', 'rb') as f:
						body = f.read()
					content_type = 'text/javascript'
				if dir_ == '/data.json':
					body = extras.to_bytes(json.dumps(s.sim.serializable(type_='http-response')))
					content_type = 'text/json'
				if dir_ == '/favicon.ico':
					os.chdir(extras.http_dir)
					with open('favicon.ico', 'rb') as f:
						body = f.read()
					content_type = 'image/x-icon'
				code = 200
			else:
				code = 404
				body = b'<html><head><title>404 Not Found</title></head><body>Requested resource not found, try the <a href="/">Homepage</a>.</body></html>'
				content_type = 'text/html'
		else:
			code = 400
			body = b'<html><head><title>Bad Request</title></head><body>Invalid HTTP GET request, try the <a href="/">Homepage</a>.</body></html>'
			content_type = 'text/html'
		header = f'''HTTP/1.1 {str(code)}
			Server: Sailboat-Simulator/{ver}
			Content-type: {content_type}
			Content-Type: {content_type}; charset=UTF-8
			Content-Length: {str(len(body))}
			Accept-Ranges: bytes
			Connection: close'''
		return extras.to_bytes(f'{header}\n\n') + body

	def quit(s) -> None:
		'''
		quits the simulation server
		:return: None
		'''
		s.running = False
		s.sim.save()
		extras.dbp('ProcManager.quit: done')

	@staticmethod
	def check_server_response(res_bytes:bytes) -> dict:
		'''
		checks if the server reported an error
		:param res_bytes: server response
		:return: dict from server (only the data, not the error flag, see simulator.Simulator.update.__doc__.return
		'''
		try:
			res_ascii = res_bytes.decode('utf-8')
		except Exception:
			raise ValueError('could not decode server response to UTF-8')
		try:
			res = json.loads(res_ascii)
		except json.JSONDecodeError as e:
			raise ValueError(f'could not deserialize server response as JSON: {str(e)}')
		assert type(res) == list
		assert len(res) == 2
		assert res[0], f'the server sent back this error message: {str(res[1])}'
		return res[1]


SERVER_INIT_TIMEOUT = 10

if __name__ == '__main__':
	print('simulator server program')
	# get user input
	# admin code
	admin_code = int(input('admin code (int): '))
	# simulation name
	sim_list = GUIs.ResourceList.get_list(type_='sims')
	print('\n'.join([f'{str(i)} -> {n}' for i, n in enumerate(sim_list)]))
	sim = sim_list[int(input('simulation number: '))]
	# port
	port = int(input('port (int): '))
	# public
	public = int(input('public (0 or 1): '))
	# create list of arguments
	args = [
		mp.Queue(),# not used
		admin_code,
		sim,
		port,
		public
	]
	procm = ProcManager(*args)
	th = threading.Thread(target=procm.main_loop)
	print('starting simulator manager thread')
	th.start()
	print(
		'\n-----------------------------------\n' +\
		f'The server is running {procm.sim.sim_name} on port {str(procm.port)} with an IPv4 address of {procm.ip},\n' +\
		f'paste http://{procm.ip}:{str(procm.port)} into your browser for the simulation preview page.\n' +\
		'-----------------------------------'
	)
	try:
		input('press enter or Ctrl-C to quit')
	except KeyboardInterrupt:
		pass
	procm.quit()
	th.join()
