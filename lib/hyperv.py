#!/usr/bin/env python

## Copyright (c) 2014 Citrix Systems, Inc. All Rights Reserved.
## You may only reproduce, distribute, perform, display, or prepare derivative works of this file pursuant to a valid license from Citrix.

from ConfigParser import ConfigParser
import os
import sys
import winrm

# setup the conf object and set default values...
conf = ConfigParser()
conf.add_section('HYPERV')
conf.set('HYPERV', 'module_path', 'C:\Program Files\modules\HyperV')
conf.set('HYPERV', 'logging', 'True')
conf.set('HYPERV', 'log_file', './logs/hyperv_ps.log')

# read in config if it exists
conf.read("./settings-hyperv.conf")

# require 'endpoint', 'username' and 'password' to use this lib
if not conf.has_option('HYPERV', 'endpoint'):
	sys.exit("Config required in settings-hyperv.conf: [HYPERV] -> endpoint")
if not conf.has_option('HYPERV', 'username'):
	sys.exit("Config required in settings-hyperv.conf: [HYPERV] -> username")
if not conf.has_option('HYPERV', 'password'):
	sys.exit("Config required in settings-hyperv.conf: [HYPERV] -> password")

class HyperV:
	VM_RUNNING = 2
	VM_STOPPED = 3

	def __init__(self, endpoint, username, password):
		self.session = winrm.Session(endpoint, auth=(username, password))

	# takes a powershell command and runs it on a hyperv server.
	def powershell(self, command):
		ok = False
		cmd = 'powershell -Command "Import-Module \'%s\'; %s | Format-List"' % (conf.get('HYPERV', 'module_path'), command.replace('"', '\\\"'))
		r = self.session.run_cmd(cmd)
		if conf.getboolean('HYPERV', 'logging'):
			with open(conf.get('HYPERV', 'log_file'), 'a') as f:
				f.write('request:\n')
				f.write(cmd)
				f.write('\n\n')
				f.write('response:')
				f.write(r.std_out)
				f.write('\n\n\n')
		if r.status_code == 0:
			ok = True
		objs = []
		for raw_obj in [x for x in r.std_out.split('\r\n\r\n') if x != '']: # loop through the objects that are not empty
			obj = {} # the object to be populated with the elements
			elements = raw_obj.split('\r\n') # for now, assume each element is on its own row
			key = None # if the element wraps, this will point to the correct element
			for element in elements:
				el_parts = element.split(' : ', 1) # split the line on the first ':' only
				if len(el_parts) > 1: # standard case when there is a key and value on the same line
					key = el_parts[0].strip()
					obj[key] = el_parts[1].strip()
				else: # no key, so the key was the previous element, so append to that result
					if key:
						obj[key] = obj[key] + el_parts[0].strip()
			objs.append(obj) # add the object to the array
		if ok:
			return objs, ok
		else:
			return r.std_err, ok

### Set the hyperv object to be used elsewhere
hyperv = HyperV(conf.get('HYPERV', 'endpoint'), conf.get('HYPERV', 'username'), conf.get('HYPERV', 'password'))

### Update the running-hyperv.conf file
conf.read("./running-hyperv.conf") # make sure we have everything from this file already
with open('running-hyperv.conf', 'wb') as f:
	conf.write(f) # update the file to include any changes we have made

