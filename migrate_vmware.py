#!/usr/bin/env python

from ConfigParser import ConfigParser
from pysphere import VIServer
from lib.cloudstack import cs
import json
import logging
import os
import re
import subprocess
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

conf.set('VMWARE', 'log_file', './logs/vmware-%s.log' % (conf.get('STATE', 'migration_timestamp')))
with open('running.conf', 'wb') as f:
	conf.write(f) # update the file to include the changes we have made

# add migration logging
log = logging.getLogger()
log_handler = logging.FileHandler(conf.get('VMWARE', 'log_file'))
log_format = logging.Formatter('%(asctime)s %(levelname)s: %(message)s')
log_handler.setFormatter(log_format)
log.addHandler(log_handler) 
log.setLevel(logging.INFO)

conf.set('STATE', 'migrate_error', 'False')

def export_vm(vm_id):
	vms = json.loads(conf.get('STATE', 'vms'))
	log.info('EXPORTING %s' % (vms[vm_id]['src_name']))
	vms[vm_id]['clean_name'] = re.sub('[^0-9a-zA-Z]+', '-', vms[vm_id]['src_name'])
	cmd = ['ovftool'] # command
	cmd.append('-tt=OVA') # output format
	cmd.append('-n=%s' % (vms[vm_id]['clean_name'])) # target name
	cmd.append('vi://%s:%s@%s/%s?ds=%s' % (
		conf.get('VMWARE', 'username').replace('@', '%40').replace('\\', '%5c').replace('!', '%21'), 
		conf.get('VMWARE', 'password').replace('@', '%40').replace('\\', '%5c').replace('!', '%21'),
		conf.get('VMWARE', 'endpoint'),
		vms[vm_id]['src_dc'],
		vms[vm_id]['src_path'].replace(' ', ''))) # connection details
	cmd.append('/mnt/share/vhds') # destination location
	output = ''
	try:
		output = subprocess.check_output(cmd)
	except subprocess.CalledProcessError, e:
		file_path = ''
		initial_error = e.output
		for line in e.output.split('\n'):
			if 'File already exists' in line:
				file_path = line.split('File already exists: ')[-1]
				break
		if file_path:
			log.info('Export file already exists.  Attempting to remove it so we can do a clean export...')
			rm_error = False
			try:
				os.remove(file_path)
			except:
				rm_error = True
				conf.set('STATE', 'migrate_error', 'True')
				log.error('Failed to remove the existing export file...')
				log.error('Could not export %s... \n%s' % (vms[vm_id]['src_name'], initial_error))
			if not rm_error:
				log.info('File removed successfully.  Attempting to export again...')
				try:
					output = subprocess.check_output(cmd)
				except subprocess.CalledProcessError, e:
					log.error('Could not export %s... \n%s' % (vms[vm_id]['src_name'], e.output))
					conf.set('STATE', 'migrate_error', 'True')
		else:
			log.error('Could not export %s... \n%s' % (vms[vm_id]['src_name'], e.output))
			conf.set('STATE', 'migrate_error', 'True')
	if not conf.getboolean('STATE', 'migrate_error'):
		log.info('Finished exporting %s' % (vms[vm_id]['src_name']))
		vms[vm_id]['state'] = 'exported'
		conf.set('STATE', 'vms', json.dumps(vms))
		with open('running.conf', 'wb') as f:
			conf.write(f) # update the file to include the changes we have made


def import_vm(vm_id):
	# import the vm
	vms = json.loads(conf.get('STATE', 'vms'))
	log.info('IMPORTING %s' % (vms[vm_id]['src_name']))

def launch_vm(vm_id):
	# launch the new vm
	vms = json.loads(conf.get('STATE', 'vms'))
	log.info('LAUNCHING %s' % (vms[vm_id]['src_name']))

# run the actual migration
def do_migration():
	vms = json.loads(conf.get('STATE', 'vms'))
	migrate = json.loads(conf.get('STATE', 'migrate'))
	for vm_id in migrate[:]: # makes a copy of the list so we can delete from the original
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
	if conf.getboolean('STATE', 'migrate_error'):
		log.info('Finished with ERRORS!!!\n\n')
	else:
		log.info('ALL FINISHED!!!\n\n')

	log.info('~~~ ~~~ ~~~ ~~~')

	# cleanup settings that need to be refereshed each run
	conf.remove_option('STATE', 'migrate_error')

