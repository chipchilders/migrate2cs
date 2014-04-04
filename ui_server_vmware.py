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

	if conf.has_option('STATE', 'vm_order'):
		order = json.loads(conf.get('STATE', 'vm_order'))
	else:
		order = []

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
	datacenters = vmware.get_datacenters()
	for dc_key, dc_name in datacenters.iteritems():
		src_vm_list = vmware.get_registered_vms(datacenter=dc_name)
		for vm_path in src_vm_list:
			src_vm = vmware.get_vm_by_path(vm_path)
			properties = src_vm.get_properties()
			vm_id = hashlib.sha1(properties['name']+"|"+properties['path']).hexdigest()
			if vm_id not in order:
				order.append(vm_id)
			vm = {
				'id':vm_id,
				'src_dc':dc_name,
				'src_name':properties['name'], 
				'src_path':properties['path'],
				'src_memory':properties['memory_mb'],
				'src_cpus':properties['num_cpu'],
				'src_type':properties['guest_full_name'],
				'src_disks':[],
				'src_status':src_vm.get_status(basic_status=True)
			}
			for disk in properties['disks']:
				vm['src_disks'].append({'label':disk['label'], 'path':disk['descriptor'], 'type':disk['device']['type']})

			if '64-bit' in vm['src_type'].lower():
				vm['src_os_arch'] = 64
			elif '32-bit' in vm['src_type'].lower():
				vm['src_os_arch'] = 32

			##pprint.pprint(properties)
			#print("Name: %s" % vm['src_name'])
			#print("Path: %s" % vm['src_path'])
			#print("Memory: %s" % vm['src_memory'])
			#print("CPU: %s" % vm['src_cpus'])
			#print("Type: %s" % vm['src_type'])
			#print("Disks:")
			#for disk in vm['src_disks']:
			#	print(" - %s : %s (%s)" % (disk['label'], disk['path'], disk['type']))
			#print("")
			vms[vm_id] = vm

	### Update the running.conf file
	conf.set('STATE', 'vms', json.dumps(vms))
	conf.set('STATE', 'vm_order', json.dumps(order))
	with open('running.conf', 'wb') as f:
		conf.write(f) # update the file to include the changes we have made
	return vms, order

def export_to_ova(vm):
	conf.read(['./running.conf'])
	clean_user = conf.get('VMWARE', 'username').replace('@', '%40').replace('\\', '%5c').replace('!', '%21')
	clean_pass = conf.get('VMWARE', 'password').replace('@', '%40').replace('\\', '%5c').replace('!', '%21')
	cmd = 'ovftool -tt=OVA "vi://%s:%s@%s/%s?ds=%s" %s' % (
		clean_user, 
		clean_pass,
		conf.get('VMWARE', 'endpoint'),
		vm['src_dc'],
		vm['src_path'].replace(' ', ''),
		'~/ovas'
	)


# migration page
@bottle.route('/')
@bottle.view('index')
def index():
	variables = {}
	variables['cs_objs'] = json.dumps(cs_discover_accounts())
	vms, order = discover_src_vms()
	variables['vms'] = json.dumps(vms)
	variables['vm_order'] = json.dumps(order)
	return dict(variables)


# start the server
bottle.run(
	server='rocket',
	host='0.0.0.0',
	port=8787,
	reloader=True,
	debug=False)
