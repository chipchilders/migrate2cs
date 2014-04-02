#!/usr/bin/env python

## ----------------------
##  INSTALL DEPENDANCIES
## ----------------------
## $ pip install bottle
## $ pip install rocket
##
## Author: Will Stevens <wstevens@cloudops.com>

import hashlib
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
		print("")
		print("UNABLE TO CONNECT TO VMWARE...")
		print("")
		bottle.abort(500, "Unable to connect to VMware...")
	src_vm_list = vmware.get_registered_vms()
	for vm_path in src_vm_list:
		src_vm = vmware.get_vm_by_path(vm_path)
		properties = src_vm.get_properties()
		vm_id = hashlib.sha1(properties['name']+"|"+properties['path']).hexdigest()
		vm = {
			'id':vm_id,
			'src_name':properties['name'], 
			'src_path':properties['path'],
			'src_memory':properties['memory_mb'],
			'src_cpus':properties['num_cpu'],
			'src_type':properties['guest_full_name'],
			'src_disks':[]
		}
		for disk in properties['disks']:
			vm['src_disks'].append({'label':disk['label'], 'path':disk['descriptor'], 'type':disk['device']['type']})

		#pprint.pprint(properties)
		print("Name: %s" % vm['src_name'])
		print("Path: %s" % vm['src_path'])
		print("Memory: %s" % vm['src_memory'])
		print("CPU: %s" % vm['src_cpus'])
		print("Type: %s" % vm['src_type'])
		print("Disks:")
		for disk in vm['src_disks']:
			print(" - %s : %s (%s)" % (disk['label'], disk['path'], disk['type']))
		print("")

		vms[vm_id] = vm
		### Update the running.conf file
		conf.set('STATE', 'vms', json.dumps(vms))
		with open('running.conf', 'wb') as f:
			conf.write(f) # update the file to include the changes we have made
		return vms



# migration page
@bottle.route('/')
@bottle.view('index')
def index():
	variables = {}
	variables['cs_objs'] = json.dumps(cs_discover_accounts())
	variables['vms'] = json.dumps(discover_src_vms())
	return dict(variables)


# start the server
bottle.run(
	server='rocket',
	host='0.0.0.0',
	port=8787,
	reloader=True,
	debug=False)
