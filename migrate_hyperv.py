#!/usr/bin/env python

## Copyright (c) 2014 Citrix Systems, Inc. All Rights Reserved.
## You may only reproduce, distribute, perform, display, or prepare derivative works of this file pursuant to a valid license from Citrix.

from ConfigParser import ConfigParser
from lib.hyperv import HyperV # the class
from lib.hyperv import hyperv # the connection
from lib.cloudstack import cs
import json
import hashlib
import ntpath
import os
import pprint
import sys
import time

# setup the conf object and set default values...
conf = ConfigParser()
conf.add_section('HYPERV')
conf.set('HYPERV', 'migration_input_file', './input/migrate_hyperv_input.json')
conf.set('HYPERV', 'pscp_exe', 'C:\pscp.exe')

# read in config files if they exists
conf.read(['./settings.conf', './running.conf'])

if not conf.has_section('STATE'):
	conf.add_section('STATE') # STATE config section to maintain state of the running process
if not conf.has_option('STATE', 'exported'):
	conf.set('STATE', 'exported', '[]') # parsed with: json.loads(conf.get('STATE', 'exported'))
if not conf.has_option('STATE', 'imported'):
	conf.set('STATE', 'imported', '[]') # parsed with: json.loads(conf.get('STATE', 'imported'))
if not conf.has_option('STATE', 'started'):
	conf.set('STATE', 'started', '[]') # parsed with: json.loads(conf.get('STATE', 'started'))
if not conf.has_option('STATE', 'vms'):
	conf.set('STATE', 'vms', '[]') # parsed with: json.loads(conf.get('STATE', 'vms'))


# copy vhd files to the file server
def copy_vhd_to_file_server(vhd_path, vhd_name):
	return hyperv.powershell('%s -l %s -pw %s "%s" %s:%s/%s' % (
		conf.get('HYPERV', 'pscp_exe'),
		conf.get('FILESERVER', 'username'),
		conf.get('FILESERVER', 'password'),
		vhd_path,
		conf.get('FILESERVER', 'host'),
		conf.get('FILESERVER', 'files_path'),
		vhd_name
	))


# run the actual migration
def do_migration():
	# comment out the following line to keep a history of the requests over multiple runs of this file.
	open(conf.get('HYPERV', 'log_file'), 'w').close() # cleans the powershell requests log before execution so it only includes this run.
	open(conf.get('CLOUDSTACK', 'log_file'), 'w').close() # cleans the cloudstack requests log before execution so it only includes this run.

	vm_input = []
	if os.path.exists(conf.get('HYPERV', 'migration_input_file')):
		with open(conf.get('HYPERV', 'migration_input_file'), 'r') as f:
			try:
				vm_input = json.load(f)
			except:
				print sys.exc_info()
				sys.exit("Error in the formatting of '%s'" % (conf.get('HYPERV', 'migration_input_file')))

	print('\n-----------------------\n-- RUNNING VM EXPORT --\n-----------------------')
	# collect data about the VMs from HyperV and populate a list of VMs

	# initialize the 'vms' variable from the existing config...
	vms = json.loads(conf.get('STATE', 'vms'))

	if vm_input: # make sure there is data in the file
		for vm_in in vm_input: # loop through the vms in the file
			# make sure the minimum fields were entered and they have not been processed already
			vm_id = hashlib.sha1(vm_in['hyperv_server']+"|"+vm_in['hyperv_vm_name']).hexdigest()
			if 'hyperv_vm_name' in vm_in and 'hyperv_server' in vm_in and vm_id not in json.loads(conf.get('STATE', 'exported')):
				objs, ok = hyperv.powershell('Get-VM -Name "%s" -Server "%s"' % (vm_in['hyperv_vm_name'], vm_in['hyperv_server']))
				if objs and ok: # make sure it found the specified VM
					print('\nEXPORTING %s\n%s' % (vm_in['hyperv_vm_name'], '----------'+'-'*len(vm_in['hyperv_vm_name'])))

					exported = False
					vm_raw = objs[0]
					vm_out = vm_in
					vm_out['id'] = vm_id
					
					# get cores
					cpu, ok = hyperv.powershell('Get-VMCPUCount -VM "%s" -Server "%s"' % (vm_in['hyperv_vm_name'], vm_in['hyperv_server']))
					if ok:
						vm_out['cores'] = int(cpu[0]['ProcessorsPerSocket']) * int(cpu[0]['SocketCount'])
					else:
						print('Get-VMCPUCount powershell command failed on %s' % (vm_in['hyperv_vm_name']))
						print('ERROR: Check the "%s" log for details' % (conf.get('HYPERV', 'log_file')))

					# get memory
					memory, ok = hyperv.powershell('Get-VMMemory -VM "%s" -Server "%s"' % (vm_in['hyperv_vm_name'], vm_in['hyperv_server']))
					if ok:
						vm_out['memory'] = int(memory[0]['Reservation'])
					else:
						print('Get-VMMemory powershell command failed on %s' % (vm_in['hyperv_vm_name']))
						print('ERROR: Check the "%s" log for details' % (conf.get('HYPERV', 'log_file')))

					# record their starting state and bring down if running
					if int(vm_raw['EnabledState']) == HyperV.VM_RUNNING:
						vm_out['state'] = 'running'
						print('VM %s is Running' % (vm_in['hyperv_vm_name']))
						status, ok = hyperv.powershell('Stop-VM -VM "%s" -Server "%s" -Wait -Force' % (vm_in['hyperv_vm_name'], vm_in['hyperv_server']))
						if ok:
							print('Stopped %s' % (vm_in['hyperv_vm_name']))
						else:
							print('Stop-VM powershell command failed on %s' % (vm_in['hyperv_vm_name']))
							print('ERROR: Check the "%s" log for details' % (conf.get('HYPERV', 'log_file')))
					elif int(vm_raw['EnabledState']) == HyperV.VM_STOPPED:
						vm_out['state'] = 'stopped'
						print('VM %s is Stopped' % (vm_in['hyperv_vm_name']))
					else: # this should be improved...
						vm_out['state'] = 'unknown'
						print('VM %s is in an Unknown state' % (vm_in['hyperv_vm_name']))

					if (vm_out['state'] == 'running' and ok) or vm_out['state'] == 'stopped':
						disks, ok = hyperv.powershell('Get-VMDisk -VM "%s"' % (vm_in['hyperv_vm_name']))
						if ok:
							vm_out['disks'] = []
							for disk in disks:
								if 'DriveName' in disk and disk['DriveName'] == 'Hard Drive' and 'DiskImage' in disk:
									vm_out['disks'].append({
										'name':ntpath.split(disk['DiskImage'])[1].replace(' ', '-').split('.')[0],
										'url':'%s://%s:%s%s%s' % (
											'https' if conf.get('FILESERVER', 'port') == '443' else 'http',
											conf.get('FILESERVER', 'host'),
											conf.get('FILESERVER', 'port'),
											conf.get('FILESERVER', 'base_uri'),
											ntpath.split(disk['DiskImage'])[1].replace(' ', '-')
											)
										})
									print('Copying drive %s' % (disk['DiskImage']))
									exported = True
									result, ok = copy_vhd_to_file_server(disk['DiskImage'], ntpath.split(disk['DiskImage'])[1].replace(' ', '-'))
									if ok:
										print('Finished copy...')
										exported = True
									else:
										print('Copy failed...')
										print('ERROR: Check the "%s" log for details' % (conf.get('HYPERV', 'log_file')))
						else:
							print('Get-VMDisk powershell command failed on %s' % (vm_in['hyperv_vm_name']))
							print('ERROR: Check the "%s" log for details' % (conf.get('HYPERV', 'log_file')))

					# bring the machines back up that were running now that we copied their disks
					if vm_out['state'] == 'running':
						status, ok = hyperv.powershell('Start-VM -VM "%s" -Server "%s" -Wait -Force' % (vm_in['hyperv_vm_name'], vm_in['hyperv_server']))
						if ok:
							print('Re-Started VM %s' % (vm_in['hyperv_vm_name']))
						else:
							print('Failed to restart the server.')
							print('ERROR: Check the "%s" log for details' % (conf.get('HYPERV', 'log_file')))

					print('Finished exporting %s' % (vm_in['hyperv_vm_name']))

					if exported:
						vms.append(vm_out)

						### Update the running.conf file
						conf.read("./running.conf") # make sure we have everything from this file already
						exported = json.loads(conf.get('STATE', 'exported'))
						exported.append(vm_out['id'])
						conf.set('STATE', 'exported', json.dumps(exported, indent=4, sort_keys=True))
						conf.set('STATE', 'vms', json.dumps(vms, indent=4, sort_keys=True))
						with open('running.conf', 'wb') as f:
							conf.write(f) # update the file to include the changes we have made

	print "\nCurrent VM Objects:"
	pprint.pprint(vms)

	print('\n\n-----------------------\n-- RUNNING VM IMPORT --\n-----------------------')
	# go through the VMs and import them into CS
	for i, vm in enumerate(vms):
		vm_id = hashlib.sha1(vm['hyperv_server']+"|"+vm['hyperv_vm_name']).hexdigest()
		if vm_id not in json.loads(conf.get('STATE', 'imported')):
			print('\nIMPORTING %s\n%s' % (vm['hyperv_vm_name'], '----------'+'-'*len(vm['hyperv_vm_name'])))
			imported = False

			## setup the cloudstack details we know (or are using defaults for)
			if 'cs_zone' not in vm and conf.has_option('CLOUDSTACK', 'default_zone'):
				vm['cs_zone'] = conf.get('CLOUDSTACK', 'default_zone')
				zone = cs.request(dict({'command':'listZones', 'id':vm['cs_zone']}))
				if zone and 'zone' in zone and len(zone['zone']) > 0:
					if zone['zone'][0]['networktype'] == 'Basic':
						vm['cs_zone_network'] = 'basic'
					else:
						vm['cs_zone_network'] = 'advanced'

			if 'cs_domain' not in vm and conf.has_option('CLOUDSTACK', 'default_domain'):
				vm['cs_domain'] = conf.get('CLOUDSTACK', 'default_domain')

			if 'cs_account' not in vm and conf.has_option('CLOUDSTACK', 'default_account'):
				vm['cs_account'] = conf.get('CLOUDSTACK', 'default_account')

			if 'cs_network' not in vm and conf.has_option('CLOUDSTACK', 'default_network'):
				vm['cs_network'] = conf.get('CLOUDSTACK', 'default_network')

			if 'cs_additional_networks' not in vm and conf.has_option('CLOUDSTACK', 'additional_networks'):
				vm['cs_additional_networks'] = conf.get('CLOUDSTACK', 'additional_networks')

			if 'cs_service_offering' not in vm and conf.has_option('CLOUDSTACK', 'default_service_offering'):
				vm['cs_service_offering'] = conf.get('CLOUDSTACK', 'default_service_offering')


			# make sure we have a complete config before we start
			if ('cs_zone' in vm and 'cs_domain' in vm and 'cs_account' in vm and 'cs_network' in vm and 'cs_service_offering' in vm):
				# manage the disks
				if 'disks' in vm and len(vm['disks']) > 0:
					# register the first disk as a template since it is the root disk
					print('Creating template for root volume \'%s\'...' % (vm['disks'][0]['name']))
					template = cs.request(dict({
						'command':'registerTemplate',
						'name':vm['disks'][0]['name'].replace(' ', '-'),
						'displaytext':vm['disks'][0]['name'],
						'format':'VHD',
						'hypervisor':'Hyperv',
						'ostypeid':'138', # None
						'url':vm['disks'][0]['url'],
						'zoneid':vm['cs_zone'],
						'domainid':vm['cs_domain'],
						'account':vm['cs_account']
					}))
					if template:
						print('Template \'%s\' created...' % (template['template'][0]['id']))
						vm['cs_template_id'] = template['template'][0]['id']
						imported = True
					else:
						print('ERROR: Check the "%s" log for details' % (conf.get('CLOUDSTACK', 'log_file')))

					# check if there are data disks
					if len(vm['disks']) > 1:
						# upload the remaining disks as volumes
						for disk in vm['disks'][1:]:
							imported = False # reset because we have more to do...
							print('Uploading data volume \'%s\'...' % (disk['name']))
							volume = cs.request(dict({
								'command':'uploadVolume',
								'name':disk['name'].replace(' ', '-'),
								'format':'VHD',
								'url':disk['url'],
								'zoneid':vm['cs_zone'],
								'domainid':vm['cs_domain'],
								'account':vm['cs_account']
							}))
							if volume and 'jobresult' in volume and 'volume' in volume['jobresult']:
								volume_id = volume['jobresult']['volume']['id']
								print('Volume \'%s\' uploaded...' % (volume_id))
								if 'cs_volumes' in vm:
									vm['cs_volumes'].append(volume_id)
								else:
									vm['cs_volumes'] = [volume_id]
								imported = True
							else:
								print('ERROR: Check the "%s" log for details' % (conf.get('CLOUDSTACK', 'log_file')))
			else:
				print('We are missing settings fields for %s' % (vm['hyperv_vm_name']))

			if imported:
				### Update the running.conf file
				conf.read("./running.conf") # make sure we have everything from this file already
				imported = json.loads(conf.get('STATE', 'imported'))
				imported.append(vm['id'])
				conf.set('STATE', 'imported', json.dumps(imported, indent=4, sort_keys=True))
				conf.set('STATE', 'vms', json.dumps(vms, indent=4, sort_keys=True))
				with open('running.conf', 'wb') as f:
					conf.write(f) # update the file to include the changes we have made

	print('\n\n----------------------------\n-- LAUNCHING IMPORTED VMS --\n----------------------------')
	# go through the imported VMs and start them and attach their volumes if they have any
	poll = 1
	has_error = False
	while len(json.loads(conf.get('STATE', 'started'))) != len(json.loads(conf.get('STATE', 'imported'))) and not has_error:
		for i, vm in enumerate(vms):
			vm_id = hashlib.sha1(vm['hyperv_server']+"|"+vm['hyperv_vm_name']).hexdigest()
			isAVm = 'cs_service_offering' in vm
			print("__________%s is a vm: %s________________________" % (vm_id, isAVm))
			if vm_id not in json.loads(conf.get('STATE', 'started')) and 'cs_service_offering' in vm:
				print("__________processing vm: %s________________________" % vm_id)
				# check if the template has finished downloading...
				template = cs.request(dict({
					'command':'listTemplates', 
					'listall':'true', 
					'templatefilter':'self', 
					'id':vm['cs_template_id']
				}))
				if template and 'template' in template and len(template['template']) > 0:
					if template['template'][0]['isready']: # template is ready
						volumes_ready = True
						if 'cs_volumes' in vm and len(vm['cs_volumes']) > 0: # check if volumes are ready
							for volume_id in vm['cs_volumes']:
								volume = cs.request(dict({
									'command':'listVolumes', 
									'listall':'true', 
									'id':volume_id
								}))
								if volume and 'volume' in volume and len(volume['volume']) > 0:
									# check the state of the volume
									if volume['volume'][0]['state'] != 'Uploaded' and volume['volume'][0]['state'] != 'Ready':
										print('%s: %s is waiting for volume \'%s\', current state: %s' % 
											(poll, vm['hyperv_vm_name'], volume['volume'][0]['name'], volume['volume'][0]['state']))
										volumes_ready = False
									else:
										volumes_ready = volumes_ready and True # propogates False if any are False
						# everything should be ready for this VM to be started, go ahead...
						if volumes_ready:
							print('%s: %s is ready to launch...' % (poll, vm['hyperv_vm_name']))
							print('Launching VM \'%s\'...' % (vm['hyperv_vm_name'].replace(' ', '-')))
							# create a VM instance using the template
							cmd = dict({
								'command':'deployVirtualMachine',
								'displayname':vm['hyperv_vm_name'].replace(' ', '-').replace('_', '-'),
								'templateid':vm['cs_template_id'],
								'serviceofferingid':vm['cs_service_offering'],
								'zoneid':vm['cs_zone'],
								'domainid':vm['cs_domain'],
								'account':vm['cs_account']
							})
							if vm['cs_zone_network'] == 'advanced': # advanced: so pass the networkids too
								all_networkIds = [vm['cs_network'], vm['cs_additional_networks']]
								cmd['networkids'] = ",".join(all_networkIds)
								print("_____networks: %s_________" % cmd['networkids'])
							
							cs_vm = cs.request(cmd) # launch the VM


							if cs_vm and 'jobresult' in cs_vm and 'virtualmachine' in cs_vm['jobresult']:
								#print('VM \'%s\' started...' % (template['template'][0]['id']))
								#vm['cs_template_id'] = template['template'][0]['id']
								### Update the running.conf file
								conf.read("./running.conf") # make sure we have everything from this file already
								started = json.loads(conf.get('STATE', 'started'))
								started.append(vm['id'])
								conf.set('STATE', 'started', json.dumps(started))
								conf.set('STATE', 'vms', json.dumps(vms))
								with open('running.conf', 'wb') as f:
									conf.write(f) # update the file to include the changes we have made

								# attach the data volumes to it if there are data volumes
								#if 'cs_volumes' in vm and len(vm['cs_volumes']) > 0:
								#	attach_volume = cs.request(dict({
								#	'command':'attachVolume',
								#	'displayname':vm['hyperv_vm_name'].replace(' ', '-'),
								#	'templateid':vm['cs_template_id'],
								#	'serviceofferingid':vm['cs_service_offering'],
								#	'networkids':vm['cs_network'],
								#	'zoneid':vm['cs_zone'],
								#	'domainid':vm['cs_domain'],
								#	'account':vm['cs_account']
								#}))
							elif cs_vm and 'jobresult' in cs_vm and 'errortext' in cs_vm['jobresult']:
								print('%s failed to start!  ERROR: %s' % (vm['hyperv_vm_name'], cs_vm['jobresult']['errortext']))
								has_error = True
							else:
								print('%s did not Start or Error correctly...' % (vm['hyperv_vm_name']))
								has_error = True
								

					else:
						print('%s: %s is waiting for template, current state: %s'% (poll, vm['hyperv_vm_name'], template['template'][0]['isready']))
		print('... sleeping ...')
		poll = poll + 1
		time.sleep(10)

	### clean up the running.conf file...
	#os.remove('./running.conf')


if __name__ == "__main__":
	do_migration()
	print('\n\nALL FINISHED!!!\n\n')

