#!/usr/bin/env python

## ----------------------
##  INSTALL DEPENDANCIES
## ----------------------
## $ pip install bottle
## $ pip install rocket or cherrypy
##
## Author: Will Stevens <wstevens@cloudops.com>

import hashlib
import json
import logging
import logging.handlers
import pprint
from pysphere import VIServer
from ui_common import *

conf = ConfigParser()
conf.add_section('VMWARE')
conf.add_section('WEBSERVER')
conf.set('WEBSERVER', 'debug', 'False')
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


# add server logging
log_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger()
if conf.getboolean('WEBSERVER', 'debug'):
    log.setLevel(logging.DEBUG)
else:
    log.setLevel(logging.INFO)
logging.basicConfig(format='%(asctime)s %(message)s')
log_file_handler = logging.handlers.TimedRotatingFileHandler('server.log', when='midnight', interval=1, backupCount=30)
log_file_handler.setFormatter(log_formatter)
log.addHandler(log_file_handler)


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
			if vm_id not in vms:
				vms[vm_id] = {}

			vms[vm_id]['id'] = vm_id
			vms[vm_id]['state'] = ''
			vms[vm_id]['src_dc'] = dc_name
			vms[vm_id]['src_name'] = properties['name'] 
			vms[vm_id]['src_path'] = properties['path']
			vms[vm_id]['src_memory'] = properties['memory_mb']
			vms[vm_id]['src_cpus'] = properties['num_cpu']
			vms[vm_id]['src_type'] = properties['guest_full_name']
			vms[vm_id]['src_disks'] = []
			vms[vm_id]['src_status'] = src_vm.get_status(basic_status=True)

			for disk in properties['disks']:
				vms[vm_id]['src_disks'].append({
					'label':disk['label'], 
					'path':disk['descriptor'], 
					'type':disk['device']['type'],
					'size':disk['capacity']
				})

			if '64-bit' in vms[vm_id]['src_type'].lower():
				vms[vm_id]['src_os_arch'] = 64
			elif '32-bit' in vms[vm_id]['src_type'].lower():
				vms[vm_id]['src_os_arch'] = 32

			##pprint.pprint(properties)
			#print("Name: %s" % vms[vm_id]['src_name'])
			#print("Path: %s" % vms[vm_id]['src_path'])
			#print("Memory: %s" % vms[vm_id]['src_memory'])
			#print("CPU: %s" % vms[vm_id]['src_cpus'])
			#print("Type: %s" % vms[vm_id]['src_type'])
			#print("Disks:")
			#for disk in vms[vm_id]['src_disks']:
			#	print(" - %s : %s (%s)" % (disk['label'], disk['path'], disk['type']))
			#print("")

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


# start the migration
@bottle.route('/migration/start', method='POST')
def start_migration():
	if bottle.request.params.migrate:
		conf.set('STATE', 'migrate', bottle.request.params.migrate)
		conf.set('STATE', 'migration_timestamp', int(bottle.request.params.timestamp)/1000)
		with open('running.conf', 'wb') as f:
			conf.write(f) # update the file to include the changes we have made
		subprocess.Popen(['python', 'migrate_vmware.py'])
		return 'ok'
	else:
		return bottle.abort(500, 'Could not start the migration...')

# get the migration log
@bottle.route('/migration/log')
def get_migration_log():
	output = ''
	conf.read(['./running.conf'])
	with open(conf.get('VMWARE', 'log_file'), 'r') as f:
		output = f.read()
	return output

# start the server
bottle.run(
	server='cherrypy',
	host='0.0.0.0',
	port=8787,
	reloader=True,
	debug=conf.getboolean('WEBSERVER', 'debug'))
