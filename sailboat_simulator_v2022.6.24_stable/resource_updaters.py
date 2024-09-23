#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  resource_updaters.py
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
# builtins
import sys, os, json

# from CWD
import extras, graphics, simulator

# classes
class UpdaterSuperClass:
	'''
	updater superclass
	'''
	def __init__(s, type_:str, name:str):
		'''
		init
		:param type_: can be in ['map', 'sim']
		'''
		assert type_ in ['map', 'sim']
		s.type_ = type_
		s.name = name + '.json'
		s.dir = {'map': extras.resources.maps_dir, 'sim': extras.resources.simulations_dir}[s.type_]
		s.file_path = os.path.join(s.dir, s.name)

	def convert(s, converter_function) -> None:
		'''
		converts file to current version
		:param converter_function:
		:return: None
		'''
		os.chdir(s.dir)
		with open(s.file_path) as f:
			data = converter_function(json.loads(f.read()))
		with open(s.file_path, 'w') as f:
			f.write(json.dumps(data))


class MapUpdater(UpdaterSuperClass):
	'''
	map file updater
	'''
	def __init__(s, name:str) -> None:
		'''
		init
		:param name: map name
		'''
		super().__init__('map', name)

	def convert_subclass(s) -> None:
		'''
		converts file to current version
		:return: None
		'''
		super().convert(s.convert_data)

	def convert_data(s, data):
		'''
		actually does the converting
		:param data: deserialized input data
		:return: output to be JSON serialized
		'''
		new_landmasses = []
		for i in range(int(len(data['coastlines']) / 2)):
			coastline = data['coastlines'][i * 2]
			rep_point = data['coastlines'][i * 2 + 1]
			new_landmasses.append({
				'name': '<default-name>',
				'coords': coastline,
				'rep-point': rep_point
			})
		data['landmasses'] = new_landmasses
		del data['coastlines']
		return data


class SimUpdater(UpdaterSuperClass):
	'''
	simulation file updater
	NOTE: this must be used last since it uses map and boat files
	'''
	def __init__(s, name:str) -> None:
		'''
		init
		:param name: sim name
		'''
		super().__init__('sim', name)

	def convert_subclass(s) -> None:
		'''
		converts file to current version
		:return: None
		'''
		super().convert(s.convert_data)

	def convert_data(s, data):
		'''
		actually does the converting
		:param data: deserialized input data
		:return: output to be JSON serialized
		'''
		# default user dict
		admin_dict = simulator.ClientHandler.new(boat=data['boat']['type'], map=data['map'])
		# old and new boats dicts
		new_boat = admin_dict['boat']
		old_boat = data['boat']
		new_boat['velocity'] = old_boat['momentum']
		new_boat['pos'] = old_boat['pos']
		new_boat['angle'] = old_boat['angle']
		# put boat dict back in usr dict
		admin_dict['boat-start'] = new_boat
		admin_dict['boat'] = new_boat
		# create new dict for whole file
		new_data = {
			'map': data['map'],
			'paused': False,
			'clients': {
				'__admin__': admin_dict
			},
			'wind-settings': data['wind-settings'],
			'record': data['record'],
			'timer': extras.Timer().serializable(),
			'password': None
		}
		return new_data


def main():
	while True:
		try:
			type_, name = input('type (map, sim), name, "Q" to quit: ').split(' ')
		except Exception:
			type_ = 'Q'
		if type_ == 'Q':
			break
		if type_ == 'map':
			updater = MapUpdater(name)
		else:
			updater = SimUpdater(name)
		print(f'converting file {updater.file_path}')
		updater.convert_subclass()
		print('done\n')
	return 0

if __name__ == '__main__':
	print('Resource Updater from v2021-10-9')
	sys.exit(main())
