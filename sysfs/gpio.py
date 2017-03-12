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
	'pin'
)

import os
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


class Pin:
	self __init__(self, nr, eventLoop = None):
		if not isinstance(nr, int) or nr < 0:
			raise TypeError('Not a valid GPIO number')
		
		self.__nr = nr
		self.eventLoop = eventLoop
		
		self.__valueFile = None
		self.__monitoring = None
	
	
	############
	## Export ##
	############
	def export(self):
		with open(SYSFS_EXPORT_PATH, 'w') as f:
			f.write('%d' % self.__nr)
	
	
	def unexport(self):
		self.__closeValueFile()
		
		with open(SYSFS_UNEXPORT_PATH, 'w') as f:
			f.write('%d' % self.__nr)
	
	
	def exportedOrFail(self):
		if not self.exported:
			raise Exception('GPIO #%d is not exported' % self.__nr)
	
	
	@property
	def exported(self):
		return os.path.isdir(SYSFS_GPIO_PATH % self.__nr)
	
	
	@exported.setter
	def exported(self, shouldBeExported):
		if self.exported == shouldBeExported:
			return
		
		if shouldBeExported == True:
			self.export()
		else if shouldBeExported == False:
			self.unexport()
		else:
			raise TypeError('exported is a boolean property.')
	
	
	###############
	## Direction ##
	###############
	def configureAsOutput(self, initValue=None, inverted=False):
		self.__reconfigureMonitoring()
		
		if isinstance(inverted, bool):
			self.inverted = inverted
		else if inverted is not None
			raise TypeError('inverted has to be None, True or False.')
		
		if initValue is None:
			self._direction = 'out'
		else if initValue == True:
			self._direction = 'high'
		else if initValue == False:
			self._direction = 'low'
		else:
			raise TypeError('initValue has to be None, True or False.')
	
	
	def configureAsInput(self, cbRising=None, cbFalling=None):
		if cbRising is None and cbFalling is None:
			edge = 'none'
		else if callable(cbRising) and cbFalling is None:
			edge = 'rising'
		else if cbRising is None and callable(cbFalling):
			edge = 'falling'
		else if callable(cbRising) and callable(cbFalling):
			edge = 'both'
		else
			raise TypeError('The callbacks have to be None or a callable.')
		
		self.__reconfigureMonitoring()
		
		try:
			with open(SYSFS_GPIO_EDGE_PATH % self.__nr, 'w') as f:
				return f.write(edge)
		
		except FileNotFoundError:
			if edge != 'none':
				self.exportedOrFail()
				raise Exception('GPIO #%d does not support callbacks.' % self.__nr)
		
		self._direction = 'in'
		
		self.__reconfigureMonitoring(cbRising, cbFalling)
	
	
	@property
	def _direction(self):
		try:
			with open(SYSFS_GPIO_DIRECTION_PATH % self.__nr, 'r') as f:
				return f.read()[:-1]
		
		except FileNotFoundError:
			self.exportedOrFail()
			raise Exception('GPIO #%d has a fixed direction. It can not be obtained.' % self.__nr)
	
	
	@_direction.setter
	def _direction(self, direction):
		try:
			with open(SYSFS_GPIO_DIRECTION_PATH % self.__nr, 'w') as f:
				return f.write(direction)
		
		except FileNotFoundError:
			self.exportedOrFail()
			raise Exception('GPIO #%d has a fixed direction. It can not be changed.' % self.__nr)
	
	
	@property
	def isInput(self):
		return self.direction == 'in'
	
	
	@property
	def isOutput(self):
		return not self.isInput
	
	
	###########
	## Value ##
	###########
	def __assureValueFile(self):
		if self.__valueFile is None:
			self.__valueFile = open(SYSFS_GPIO_VALUE_PATH % self.__nr, 'r+')
	
	
	def __closeValueFile(self):
		if self.__valueFile is not None:
			self.__reconfigureMonitoring()
			
			self.__valueFile.close()
			self.__valueFile = None
	
	
	@property
	def value(self):
		self.__assureValueFile()
		self.__valueFile.seek(0)
		return self.__valueFile.read()[:-1] != '0'
	
	
	@value.setter
	def value(self, value):
		self.__assureValueFile()
		self.__valueFile.seek(0)
		
		else if value == True:
			self.__valueFile.write('1')
		else if value == False:
			self.__valueFile.write('0')
		else:
			raise TypeError('value has to be True or False')
	
	
	################
	## Active Low ##
	################
	@property
	def inverted(self):
		with open(SYSFS_GPIO_ACTIVE_LOW_PATH % self.__nr, 'r') as f:
			return f.read()[:-1] != '0'
	
	
	@inverted.setter
	def inverted(self, inverted):
		with open(SYSFS_GPIO_ACTIVE_LOW_PATH % self.__nr, 'w') as f:
			else if inverted == True:
				f.write('1')
			else if inverted == False:
				f.write('0')
			else:
				raise TypeError('inverted has to be True or False')
	
	
	################
	## Monitoring ##
	################
	@property
	def currentEventLoop(self):
		if self.__monitoring is None:
			return None
		else:
			return self.__monitoring['eventLoop']
	
	
	def __reconfigureMonitoring(self, cbRising=None, cbFalling=None):
		if self.__monitoring is not None:
			self.__monitoring['eventLoop'].remove(self.__monitoring['token'])
			self.__monitoring = None
		
		if cbRising is None and cbFalling is None:
			return
		
		if self.eventLoop is None:
			raise Exception('Can\'t monitor GPIO %d without event loop' % self.__nr)
		
		self.__assureValueFile()
		token = self.eventLoop.add(self.__valueFile, self._interruptHandler)
		
		self.__monitoring = {
			'token': token,
			'eventLoop': self.eventLoop,
			'cbRising': cbRising,
			'cbFalling': cbFalling,
		}
	
	
	def _interruptHandler(self):
		if self.__monitoring is None:
			return
		
		val = self.value
		
		if val and callable(self.__monitoring['cbRising']):
			self.__monitoring['cbRising'](True)
		else if not val and callable(self.__monitoring['cbFalling']):
			self.__monitoring['cbFalling'](False)
	
	
	
	
#class PinCollection(collections.abc.MutableMapping):
	#def __new__(cls, *args, **kw):
		#if not hasattr(cls, '_instance'):
			#instance = super(Controller, cls).__new__(cls)
			
			#instance.__pins = {}
			
			#cls._instance = instance
		#return cls._instance
	
	
	#def __init__(self):
		#pass
	
	
	#__setitem__(self, nr, pin):
		#if nr in self.__pins:
			#if self.__pins[nr] is pin:
				#return
			#else:
				#del self[nr]
		
		#pin._associate(self, nr)
		#self.__pins[nr] = pin
	
	
	#__getitem__(self, nr):
		#if nr not in self.__pins:
			#if not isinstance(nr, int) or nr < 0:
				#raise TypeError('Not a valid GPIO number')
			
			#self[nr] = Pin()
			##else:
				##raise KeyError()
		
		#return self.__pins[nr]
	
	
	#__delitem__(self, nr):
		#if not isinstance(nr, int) or nr < 0:
			#raise TypeError('Not a valid GPIO number')
		
		#if nr not in self.__pins:
			#raise KeyError()
		
		#pin._dissociate()
		#del self.__pins[nr]
		
	
	#__iter__(self):
		#for pin in self.__pins:
			#yield pin
	
	
	#__len__(self):
		#return len(self.__pins)
		




import errno
import select
from twisted.internet import reactor

class TwistedLoop(object):
			self._poll_queue = select.epoll()
			# Cleanup before stopping reactor
			reactor.addSystemEventTrigger('before', 'shutdown', self.stop)
			
			# Run the EPoll in a Thread, as it blocks.
			reactor.callInThread(self._poll_queue_loop)
	
	
	def _poll_queue_register_pin(self, pin):
		self._poll_queue.register(pin, (select.EPOLLPRI | select.EPOLLET))
	
	
	def _poll_queue_unregister_pin(self, pin):
		self._poll_queue.unregister(pin)
	
	
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



# Create controller instance
pin = Controller()


if __name__ == '__main__':
	print("This module isn't intended to be run directly.")
