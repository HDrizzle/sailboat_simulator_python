#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  time_logging.py
#  
#  Copyright 2020 Hadrian Ward <pi@myRPiZW>
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

import time

class time_logger:
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
			s.curr_d[p_name]['times'].append(time.time())
		else:
			s.curr_d[p_name] = {'times':[time.time()], 'sub':{}}
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
				s.curr_d[p_name]['times'].append(time.time())
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