#!/usr/bin/env python

## ----------------------
##  INSTALL DEPENDANCIES
## ----------------------
## $ pip install bottle
## $ pip install rocket
##
## Author: Will Stevens <wstevens@cloudops.com>

import json
import pprint
from pysphere import VIServer
from ui_common import *

conf = ConfigParser()
conf.add_section('VMWARE')
# read in config files if they exist
conf.read(['./settings.conf', './running.conf'])

if not conf.has_section('STATE'):
	conf.add_section('STATE') # STATE config section to maintain state of the running process

# require the vmware endpoint to be configured to start the server
if not conf.has_option('VMWARE', 'endpoint'):
	sys.exit("Config required in settings.conf: [VMWARE] -> endpoint")
if not conf.has_option('VMWARE', 'username'):
	sys.exit("Config required in settings.conf: [VMWARE] -> username")
if not conf.has_option('VMWARE', 'password'):
	sys.exit("Config required in settings.conf: [VMWARE] -> password")

def discover_src_vms():
	conf.read(['./running.conf'])
	if conf.has_option('STATE', 'vms'):
		vms = json.loads(conf.get('STATE', 'vms'))
	else:
		vms = {}

	vmware = VIServer()
	try:
		vmware.connect(
			conf.get('VMWARE', 'endpoint'),
			conf.get('VMWARE', 'username'),
			conf.get('VMWARE', 'password')
		)
	except:
		return vms
	src_vm_list = vmware.get_registered_vms()
	for src_vm in src_vm_list:
		vm = vmware.get_vm_by_path(src_vm)
		properties = vm.get_properties()
		print("Name: %s" % properties.name)
		print("Path: %s" % properties.path)
		print("Memory: %s" % properties.memory_mb)
		print("CPU: %s" % properties.num_cpu)
		print("Type: %s" % properties.guest_full_name)
		print("")



# migration page
@bottle.route('/')
@bottle.view('index')
def index():
	output = {}
	output['cs_objs'] = json.dumps(cs_discover_accounts())
	discover_src_vms()
	#pprint.pprint(output['cs_objs'])
	return dict(output)


# start the server
bottle.run(
	server='rocket',
	host='0.0.0.0',
	port=8787,
	reloader=True,
	debug=False)
