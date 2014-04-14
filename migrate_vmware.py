#!/usr/bin/env python

from ConfigParser import ConfigParser
from pysphere import VIServer
from lib.cloudstack import cs
import json
import logging
import subprocess
import time
import sys
if sys.version_info < (2, 7):
	import lib.subprocess_compat
	subprocess.check_output = lib.subprocess_compat.check_output

# setup the conf object and set default values...
conf = ConfigParser()
conf.add_section('VMWARE')

# read in config files if they exists
conf.read(['./settings.conf', './running.conf'])

if not conf.has_section('STATE'):
	conf.add_section('STATE') # STATE config section to maintain state of the running process
if not conf.has_option('STATE', 'migrate'):
	conf.set('STATE', 'migrate', '[]') # parsed with: json.loads(conf.get('STATE', 'migrate'))

timestamp = int(time.time()) # int removes the fractional seconds
conf.set('VMWARE', 'log_file', './logs/vmware-'+str(timestamp)+'.log')

# add migration logging
log = logging.getLogger()
log_handler = logging.FileHandler(conf.get('VMWARE', 'log_file'))
log_format = logging.Formatter('%(asctime)s %(message)s')
log_handler.setFormatter(log_format)
log.addHandler(log_handler) 
log.setLevel(logging.INFO)


def export_vm(vm_id):
	# export the vm
	vms = json.loads(conf.get('STATE', 'vms'))
	cmd = ['ovftool'] # command
	cmd.append('-tt=OVA') # output format
	cmd.append('vi://%s:%s@%s/%s?ds=%s' % (
		conf.get('VMWARE', 'username').replace('@', '%40').replace('\\', '%5c').replace('!', '%21'), 
		conf.get('VMWARE', 'password').replace('@', '%40').replace('\\', '%5c').replace('!', '%21'),
		conf.get('VMWARE', 'endpoint'),
		vms[vm_id]['src_dc'],
		vms[vm_id]['src_path'].replace(' ', ''))) # connection details
	cmd.append('~/ovas/') # destination location
	output = ''
	try:
		output = subprocess.check_output(cmd)
	except subprocess.CalledProcessError, e:
		log.info('Failed to export %s with error: %s' % (vms[vm_id]['src_name'], e.output))
	log.info('Output is: %s' % (output))


def import_vm(vm_id):
	# import the vm
	vms = json.loads(conf.get('STATE', 'vms'))

def launch_vm(vm_id):
	# launch the new vm
	vms = json.loads(conf.get('STATE', 'vms'))

# run the actual migration
def do_migration():
	vms = json.loads(conf.get('STATE', 'vms'))
	migrate = json.loads(conf.get('STATE', 'migrate'))
	for vm_id in migrate[:]: # makes a copy of the list so we can delete from the original
		log.info('Looking at vm_id: %s' % (vm_id))
		state = vms[vm_id]['state']
		if state == '':
			export_vm(vm_id)
			import_vm(vm_id)
			launch_vm(vm_id)
		elif state == 'exported':
			import_vm(vm_id)
			launch_vm(vm_id)
		elif state == 'imported':
			launch_vm(vm_id)
		elif state == 'launched':
			migrate.remove(vm_id)
			conf.set('STATE', 'migrate', json.dumps(migrate))
			with open('running.conf', 'wb') as f:
				conf.write(f) # update the file to include the changes we have made


if __name__ == "__main__":
	do_migration()
	print('\n\nALL FINISHED!!!\n\n')

