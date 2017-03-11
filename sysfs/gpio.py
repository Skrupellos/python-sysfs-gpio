"""
Linux SysFS-based native GPIO implementation.

The MIT License (MIT)

Copyright (c) 2014 Derek Willian Stavis

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

__all__ = (
	'INPUT', 'OUTPUT', 'DIRECTIONS',
	'RISING', 'FALLING', 'BOTH', 'EDGES',
	'ACTIVE_LOW_ON', 'ACTIVE_LOW_OFF', 'ACTIVE_LOW_MODES',
	'Controller'
)

import errno
import os
import select

from twisted.internet import reactor

import logging

Logger = logging.getLogger('sysfs.gpio')
Logger.addHandler(logging.StreamHandler())
Logger.setLevel(logging.DEBUG)


#####################
## Sysfs constants ##
#####################
SYSFS_BASE_PATH            = '/sys/class/gpio'

SYSFS_EXPORT_PATH          = SYSFS_BASE_PATH + '/export'
SYSFS_UNEXPORT_PATH        = SYSFS_BASE_PATH + '/unexport'

SYSFS_GPIO_PATH            = SYSFS_BASE_PATH + '/gpio%d'
SYSFS_GPIO_DIRECTION_PATH  = SYSFS_GPIO_PATH + '/direction'
SYSFS_GPIO_EDGE_PATH       = SYSFS_GPIO_PATH + '/edge'
SYSFS_GPIO_VALUE_PATH      = SYSFS_GPIO_PATH + '/value'
SYSFS_GPIO_ACTIVE_LOW_PATH = SYSFS_GPIO_PATH + '/active_low'

SYSFS_GPIO_VALUE_LOW   = '0'
SYSFS_GPIO_VALUE_HIGH  = '1'

EPOLL_TIMEOUT = 1  ## second


######################
## Public interface ##
######################
INPUT   = 'in'
OUTPUT  = 'out'
DIRECTIONS = (INPUT, OUTPUT)

RISING  = 'rising'
FALLING = 'falling'
BOTH    = 'both'
EDGES = (RISING, FALLING, BOTH)

ACTIVE_LOW_ON  = 1
ACTIVE_LOW_OFF = 0
ACTIVE_LOW_MODES = (ACTIVE_LOW_ON, ACTIVE_LOW_OFF)



class Pin(object):
	def __init__(self, number, direction=INPUT, callback=None, edge=None, active_low=ACTIVE_LOW_OFF):
		self._number = number
		self._direction = direction
		self._callback  = callback
		self._active_low = active_low
		
		self._fd = open(self._sysfs_gpio_value_path(), 'r+')
		
		if callback and not edge:
			raise Exception('You must supply a edge to trigger callback on')
		
		with open(self._sysfs_gpio_direction_path(), 'w') as fsdir:
			fsdir.write(direction)
		
		if edge:
			with open(self._sysfs_gpio_edge_path(), 'w') as fsedge:
				fsedge.write(edge)
		
		if active_low:
			if active_low not in ACTIVE_LOW_MODES:
				raise Exception('You must supply a value for active_low which is either 0 or 1.')
			with open(self._sysfs_gpio_active_low_path(), 'w') as fsactive_low:
				fsactive_low.write(str(active_low))
	
	
	@property
	def callback(self):
		return self._callback
	
	@callback.setter
	def callback(self, value):
		self._callback = value
	
	
	@property
	def direction(self):
		return self._direction
	
	
	@property
	def value(self):
		val = self._fd.read()
		self._fd.seek(0)
		return val == b'1\n'
	
	@callback.setter
	def value(self, value):
		self._fd.write(SYSFS_GPIO_VALUE_HIGH if value else SYSFS_GPIO_VALUE_LOW)
		self._fd.seek(0)
	
	
	@property
	def number(self):
		return self._number
	
	
	@property
	def active_low(self):
		return self._active_low
	
	
	def fileno(self):
		return self._fd.fileno()
	
	
	def changed(self, state):
		if callable(self._callback):
			self._callback(self.number, state)
	
	
	#####################
	## Private Methods ##
	#####################
	def _sysfs_gpio_value_path(self):
		return SYSFS_GPIO_VALUE_PATH % self.number
	
	
	def _sysfs_gpio_direction_path(self):
		return SYSFS_GPIO_DIRECTION_PATH % self.number
	
	
	def _sysfs_gpio_edge_path(self):
		return SYSFS_GPIO_EDGE_PATH % self.number
	
	
	def _sysfs_gpio_active_low_path(self):
		return SYSFS_GPIO_ACTIVE_LOW_PATH % self.number



class Controller(object):
	def __new__(cls, *args, **kw):
		if not hasattr(cls, '_instance'):
			instance = super(Controller, cls).__new__(cls)
			instance._allocated_pins = {}
			instance._poll_queue = select.epoll()
			
			instance._available_pins = []
			instance._running = True
			
			# Cleanup before stopping reactor
			reactor.addSystemEventTrigger('before', 'shutdown', instance.stop)
			
			# Run the EPoll in a Thread, as it blocks.
			reactor.callInThread(instance._poll_queue_loop)
			
			cls._instance = instance
		return cls._instance
	
	def __init__(self):
		pass
	
	def _poll_queue_loop(self):
		while self._running:
			try:
				events = self._poll_queue.poll(EPOLL_TIMEOUT)
			except IOError as error:
				if error.errno != errno.EINTR:
					Logger.error(repr(error))
					reactor.stop()
			if len(events) > 0:
				reactor.callFromThread(self._poll_queue_event, events)
	
	
	@property
	def available_pins(self):
		return self._available_pins
	
	@available_pins.setter
	def available_pins(self, value):
		self._available_pins = value
	
	
	def stop(self):
		self._running = False
		
		try:
			values = self._allocated_pins.copy().itervalues()
		except AttributeError:
			values = self._allocated_pins.copy().values()
		for pin in values:
			self.dealloc_pin(pin.number)
	
	
	def alloc_pin(self, number, direction, callback=None, edge=None, active_low=0):
		Logger.debug('SysfsGPIO: alloc_pin(%d, %s, %s, %s, %s)'
		             % (number, direction, callback, edge, active_low))
		
		self._check_pin_validity(number)
		
		if direction not in DIRECTIONS:
			raise Exception("Pin direction %s not in %s"
			                % (direction, DIRECTIONS))
		
		if callback and edge not in EDGES:
			raise Exception("Pin edge %s not in %s" % (edge, EDGES))
		
		if not self._check_pin_already_exported(number):
			with open(SYSFS_EXPORT_PATH, 'w') as export:
				export.write('%d' % number)
		else:
			Logger.debug("SysfsGPIO: Pin %d already exported" % number)
		
		pin = Pin(number, direction, callback, edge, active_low)
		
		if direction is INPUT:
			self._poll_queue_register_pin(pin)
		
		self._allocated_pins[number] = pin
		return pin
	
	
	def _poll_queue_register_pin(self, pin):
		self._poll_queue.register(pin, (select.EPOLLPRI | select.EPOLLET))
	
	
	def _poll_queue_unregister_pin(self, pin):
		self._poll_queue.unregister(pin)
	
	
	def dealloc_pin(self, number):
		Logger.debug('SysfsGPIO: dealloc_pin(%d)' % number)
		
		if number not in self._allocated_pins:
			raise Exception('Pin %d not allocated' % number)
		
		with open(SYSFS_UNEXPORT_PATH, 'w') as unexport:
			unexport.write('%d' % number)
		
		pin = self._allocated_pins[number]
		
		if pin.direction is INPUT:
			self._poll_queue_unregister_pin(pin)
		
		del pin, self._allocated_pins[number]
	
	
	def get_pin(self, number):
		Logger.debug('SysfsGPIO: get_pin(%d)' % number)
		return self._allocated_pins[number]
	
	
	def set_pin(self, number):
		Logger.debug('SysfsGPIO: set_pin(%d)' % number)
		
		if number not in self._allocated_pins:
			raise Exception('Pin %d not allocated' % number)
		
		return self._allocated_pins[number].set()
	
	
	def reset_pin(self, number):
		Logger.debug('SysfsGPIO: reset_pin(%d)' % number)
		
		if number not in self._allocated_pins:
			raise Exception('Pin %d not allocated' % number)
		
		return self._allocated_pins[number].reset()
	
	
	def get_pin_state(self, number):
		Logger.debug('SysfsGPIO: get_pin_state(%d)' % number)
		
		if number not in self._allocated_pins:
			raise Exception('Pin %d not allocated' % number)
		
		pin = self._allocated_pins[number]
		
		if pin.direction == INPUT:
			self._poll_queue_unregister_pin(pin)
		
		val = pin.read()
		
		if pin.direction == INPUT:
			self._poll_queue_register_pin(pin)
		
		if val <= 0:
			return False
		else:
			return True
	
	
	#####################
	## Private Methods ##
	#####################
	def _poll_queue_event(self, events):
		for fd, event in events:
			if not (event & (select.EPOLLPRI | select.EPOLLET)):
				continue
			
			try:
				values = self._allocated_pins.itervalues()
			except AttributeError:
				values = self._allocated_pins.values()
			for pin in values:
				if pin.fileno() == fd:
					pin.changed(pin.read())
	
	
	def _check_pin_already_exported(self, number):
		gpio_path = SYSFS_GPIO_PATH % number
		return os.path.isdir(gpio_path)
	
	
	def _check_pin_validity(self, number):
		if number not in self._available_pins:
			raise Exception("Pin number out of range")
		
		if number in self._allocated_pins:
			raise Exception("Pin already allocated")



# Create controller instance
Controller = Controller()


if __name__ == '__main__':
	print("This module isn't intended to be run directly.")
