#!/usr/bin/env python

## Copyright (c) 2014 Citrix Systems, Inc. All Rights Reserved.
## You may only reproduce, distribute, perform, display, or prepare derivative works of this file pursuant to a valid license from Citrix.

## ----------------------
##  INSTALL DEPENDANCIES
## ----------------------
## $ pip install bottle
## $ pip install rocket or cherrypy
##
## Author: Will Stevens 

import hashlib
import json
import logging
import logging.handlers
import pprint
from lib.hyperv import HyperV # the class
from lib.hyperv import hyperv # the connection
from ui_common import *
from ConfigParser import ConfigParser
import ntpath
import os
# import sys
import time

# setup the conf object and set default values...
conf = ConfigParser()
conf.add_section('HYPERV')
conf.set('HYPERV', 'migration_input_file', './input/migrate_hyperv_input.json')
conf.set('HYPERV', 'pscp_exe', 'C:\pscp.exe')

conf.set('HYPERV', 'log_file', './logs/hyperv_api.log')
conf.add_section('WEBSERVER')
conf.set('WEBSERVER', 'debug', 'False')
conf.set('WEBSERVER', 'port', '8080')
conf.add_section('STATE') # STATE config section to maintain state of the running process
conf.set('STATE', 'active_migration', 'False')
# read in config files if they exist
conf.read(['./settings-hyperv.conf', './running-hyperv.conf'])

if not conf.has_section('STATE'):
	conf.add_section('STATE') # STATE config section to maintain state of the running process
if not conf.has_option('STATE', 'exported'):
	conf.set('STATE', 'exported', '[]') # parsed with: json.loads(conf.get('STATE', 'exported'))
if not conf.has_option('STATE', 'imported'):
	conf.set('STATE', 'imported', '[]') # parsed with: json.loads(conf.get('STATE', 'imported'))
if not conf.has_option('STATE', 'started'):
	conf.set('STATE', 'started', '[]') # parsed with: json.loads(conf.get('STATE', 'started'))


# make sure we have an nfs mount point
if not conf.has_section('FILESERVER') or not conf.has_option('FILESERVER', 'files_path'):
	sys.exit("Config required in settings-hyperv.conf: [FILESERVER] -> files_path")

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
	conf.read(['./running-hyperv.conf'])
	pprint.pprint(conf)
	if conf.has_option('STATE', 'vms'):
		# initialize the 'vms' variable from the existing config...
		vms = json.loads(conf.get('STATE', 'vms'))
		pprint.pprint("_________1_______%s________________" % vms.__class__)
	else:
		vms = {}
		pprint.pprint("________2________%s________________" % vms.__class__)

	pprint.pprint(vms.__class__)
	if conf.has_option('STATE', 'vm_order'):
		order = json.loads(conf.get('STATE', 'vm_order'))
	else:
		order = []

	with open(conf.get('HYPERV', 'log_file'), 'a') as f:
		f.write('\n\nDISCOVERING HYPERV...\n')

	discovered = [] # vms of this discovery.  we will remove the vm's from 'vms' later if they are not in this array.

	vm_input = {}
	if os.path.exists(conf.get('HYPERV', 'migration_input_file')):
		with open(conf.get('HYPERV', 'migration_input_file'), 'r') as f:
			try:
				vm_input = json.load(f)
			except:
				print sys.exc_info()
				sys.exit("Error in the formatting of '%s'" % (conf.get('HYPERV', 'migration_input_file')))

	print('\n-----------------------\n-- discovering vms... --\n-----------------------')
	# collect data about the VMs from HyperV and populate a list of VMs

	if vm_input: # make sure there is data in the file
		for vm_key in vm_input: # loop through the vms in the file
			vm_in = vm_input[vm_key]
			# make sure the minimum fields were entered and they have not been processed already
			pprint.pprint(vm_in)
			vm_id = hashlib.sha1(vm_in['hyperv_server']+"|"+vm_in['hyperv_vm_name']).hexdigest()
			pprint.pprint(vms.__class__)
			if vm_id not in order:
				order.append(vm_id)
			if vm_id not in vms:
				vms[vm_id] = {}

			if 'hyperv_vm_name' in vm_in and 'hyperv_server' in vm_in and vm_id not in json.loads(conf.get('STATE', 'exported')):
				objs, ok = hyperv.powershell('Get-VM -Name "%s" -Server "%s"' % (vm_in['hyperv_vm_name'], vm_in['hyperv_server']))
				if objs and ok: # make sure it found the specified VM
					print('\nEXPORTING %s\n%s' % (vm_in['hyperv_vm_name'], '----------'+'-'*len(vm_in['hyperv_vm_name'])))

					vm_out = vm_in
					vm_raw = objs[0]
					vm_out['id'] = vm_id
					
					vm_out['src_name'] = vm_raw['ElementName']
					vm_out['src_type'] = vm_raw['ElementName']

					# get cores, cpus
					cpu, ok = hyperv.powershell('Get-VMCPUCount -VM "%s" -Server "%s"' % (vm_in['hyperv_vm_name'], vm_in['hyperv_server']))
					if ok:
						vm_out['src_cpus'] = int(cpu[0]['ProcessorsPerSocket']) * int(cpu[0]['SocketCount'])
					else:
						print('Get-VMCPUCount powershell command failed on %s' % (vm_in['hyperv_vm_name']))
						print('ERROR: Check the "%s" log for details' % (conf.get('HYPERV', 'log_file')))

					# get memory
					memory, ok = hyperv.powershell('Get-VMMemory -VM "%s" -Server "%s"' % (vm_in['hyperv_vm_name'], vm_in['hyperv_server']))
					if ok:
						vm_out['src_memory'] = int(memory[0]['Reservation'])
					else:
						print('Get-VMMemory powershell command failed on %s' % (vm_in['hyperv_vm_name']))
						print('ERROR: Check the "%s" log for details' % (conf.get('HYPERV', 'log_file')))

					# record their starting state and bring down if running
					if int(vm_raw['EnabledState']) == HyperV.VM_RUNNING:
						vm_out['state'] = 'running'
						print('VM %s is Running' % (vm_in['hyperv_vm_name']))
					elif int(vm_raw['EnabledState']) == HyperV.VM_STOPPED:
						vm_out['state'] = 'stopped'
						print('VM %s is Stopped' % (vm_in['hyperv_vm_name']))
					else: # this should be improved...
						vm_out['state'] = 'unknown'
						print('VM %s is in an Unknown state' % (vm_in['hyperv_vm_name']))

					if (vm_out['state'] == 'running' and ok) or vm_out['state'] == 'stopped':
						disks, ok = hyperv.powershell('Get-VMDisk -VM "%s"' % (vm_in['hyperv_vm_name']))
						if ok:
							vm_out['src_disks'] = []
							for disk in disks:
								if 'DriveName' in disk and disk['DriveName'] == 'Hard Drive' and 'DiskImage' in disk:
									vm_out['src_disks'].append({
										'size': '0',
										'label': disk['DriveName'],
										'name':ntpath.split(disk['DiskImage'])[1].replace(' ', '-').split('.')[0],
										'path':'%s://%s:%s%s%s' % (
											'https' if conf.get('FILESERVER', 'port') == '443' else 'http',
											conf.get('FILESERVER', 'host'),
											conf.get('FILESERVER', 'port'),
											conf.get('FILESERVER', 'base_uri'),
											ntpath.split(disk['DiskImage'])[1].replace(' ', '-')
											)
										})
						else:
							print('Get-VMDisk powershell command failed on %s' % (vm_in['hyperv_vm_name']))
							print('ERROR: Check the "%s" log for details' % (conf.get('HYPERV', 'log_file')))

					# vms.append(vm_out)
					vms[vm_id] = vm_out

					discovered.append(vm_id)

						# loop through the 'vms' and remove any that were not discovered in this pass...
	for vm_id in vms.keys():
		if vm_id not in discovered:
			del vms[vm_id] # no longer a valid VM, so remove it...
			if vm_id in order: # remove the vm from the order list as well if it exists...
				order.remove(vm_id)

	### Update the running-hyperv.conf file
	conf.set('STATE', 'vms', json.dumps(vms, indent=4))
	conf.set('STATE', 'vm_order', json.dumps(order, indent=4))
	with open('running-hyperv.conf', 'wb') as f:
		conf.write(f) # update the file to include the changes we have made

	return vms, order


# migration page
@bottle.route('/')
@bottle.view('index')
def index():
	variables = {}
	conf.read(['./running-hyperv.conf'])
	if not conf.getboolean('STATE', 'active_migration'):
		open(conf.get('CLOUDSTACK', 'log_file'), 'w').close() # refresh the cs_request.log on reloads
		open(conf.get('HYPERV', 'log_file'), 'w').close() # refresh the hyperv_api.log on reloads
		variables['cs_objs'] = json.dumps(cs_discover_accounts())
		vms, order = discover_src_vms()
		variables['vms'] = json.dumps(vms, indent=4)
		variables['vm_order'] = json.dumps(order, indent=4)
		variables['active_migration'] = conf.get('STATE', 'active_migration').lower()
	else:
		variables['cs_objs'] = json.dumps(json.loads(conf.get('STATE', 'cs_objs')), indent=4)
		variables['vms'] = vms = json.dumps(json.loads(conf.get('STATE', 'vms')))
		variables['vm_order'] = json.dumps(json.loads(conf.get('STATE', 'vm_order')))
		variables['active_migration'] = conf.get('STATE', 'active_migration').lower()
	variables['log_list'] = get_log_list()
	return dict(variables)


# start the migration
@bottle.route('/migration/start', method='POST')
def start_migration():
	if bottle.request.params.migrate:
		conf.read(['./running-hyperv.conf'])
		conf.set('STATE', 'active_migration', 'True')
		conf.set('STATE', 'migrate', bottle.request.params.migrate)
		conf.set('STATE', 'migration_timestamp', int(bottle.request.params.timestamp)/1000)
		with open('running-hyperv.conf', 'wb') as f:
			conf.write(f) # update the file to include the changes we have made
		subprocess.Popen(['python', 'migrate_hyperv.py'])
		return 'ok'
	else:
		return bottle.abort(500, 'Could not start the migration...')

# get the migration log
@bottle.route('/migration/log')
def get_migration_log():
	output = ''
	conf.read(['./running-hyperv.conf'])
	try:
		with open(conf.get('HYPERV', 'migration_log_file'), 'r') as f:
			output = f.read()
	except:
		output = 'Log does not exist yet...'
	return output

# start the server
bottle.run(
	server='cherrypy',
	host='0.0.0.0',
	port=conf.getint('WEBSERVER', 'port'),
	reloader=False,
	debug=conf.getboolean('WEBSERVER', 'debug'))
