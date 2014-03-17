#!/usr/bin/env python

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

# setup the conf object and set default values...
conf = ConfigParser()
conf.add_section('HYPERV')
conf.set('HYPERV', 'migration_input_file', './migrate_hyperv_input.json')
conf.set('HYPERV', 'pscp_exe', 'C:\pscp.exe')

# read in config files if they exists
conf.read(['./settings.conf', './running.conf'])

conf.add_section('STATE') # STATE config section to maintain state of the running process
if not conf.has_option('STATE', 'exported'):
	conf.set('STATE', 'exported', '[]') # parsed with: json.loads(conf.get('STATE', 'exported'))
if not conf.has_option('STATE', 'imported'):
	conf.set('STATE', 'imported', '[]') # parsed with: json.loads(conf.get('STATE', 'imported'))
if not conf.has_option('STATE', 'started'):
	conf.set('STATE', 'started', '[]') # parsed with: json.loads(conf.get('STATE', 'started'))
if not conf.has_option('STATE', 'vms'):
	conf.set('STATE', 'vms', '[]') # parsed with: json.loads(conf.get('STATE', 'vms'))

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


if __name__ == "__main__":
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

	print('\n-----------------\nRUNNING VM EXPORT\n-----------------')
	# collect data about the VMs from HyperV and populate a list of VMs
	vms = []
	if vm_input: # make sure there is data in the file
		for vm_in in vm_input: # loop through the vms in the file
			# make sure the minimum fields were entered and they have not been processed already
			vm_id = hashlib.sha1(vm_in['hyperv_server']+"|"+vm_in['hyperv_vm_name']).hexdigest()
			if ('hyperv_vm_name' in vm_in and 'hyperv_server' in vm_in and vm_id not in json.loads(conf.get('STATE', 'exported'))):
				objs, ok = hyperv.powershell('Get-VM -Name "%s" -Server "%s"' % (vm_in['hyperv_vm_name'], vm_in['hyperv_server']))
				if objs and ok: # make sure it found the specified VM
					print('\nEXPORTING %s\n%s' % (vm_in['hyperv_vm_name'], '----------'+'-'*len(vm_in['hyperv_vm_name'])))

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
									#result, ok = copy_vhd_to_file_server(disk['DiskImage'], ntpath.split(disk['DiskImage'])[1].replace(' ', '-'))
									#if ok:
									#	print('Finished copy...')
									#else:
									#	print('Copy failed...')
									#	print('ERROR: Check the "%s" log for details' % (conf.get('HYPERV', 'log_file')))
						else:
							print('Get-VMDisk powershell command failed on %s' % (vm_in['hyperv_vm_name']))
							print('ERROR: Check the "%s" log for details' % (conf.get('HYPERV', 'log_file')))

					# bring the machines back up that were running now that we copied their disks
					if vm_out['state'] == 'running':
						status, ok = hyperv.powershell('Start-VM -VM "%s" -Server "%s" -Wait -Force' % (vm_in['hyperv_vm_name'], vm_in['hyperv_server']))
						if ok:
							print('Started the server since it was running at the beginning of this process.')
						else:
							print('Failed to restart the server.')
							print('ERROR: Check the "%s" log for details' % (conf.get('HYPERV', 'log_file')))

					print('Finished exporting %s' % (vm_in['hyperv_vm_name']))

					vms.append(vm_out)

					### Update the running.conf file
					conf.read("./running.conf") # make sure we have everything from this file already
					exported = json.loads(conf.get('STATE', 'exported'))
					exported.append(vm_out['id'])
					conf.set('STATE', 'exported', json.dumps(exported))
					conf.set('STATE', 'vms', json.dumps(vms))
					with open('running.conf', 'wb') as f:
						conf.write(f) # update the file to include the changes we have made

	print "\nBuilt the following details"
	pprint.pprint(vms)

	print('\n-----------------\nRUNNING VM IMPORT\n-----------------')
	# go through the VMs and import them into CS
	for i, vm in enumerate(vms):
		print('\nIMPORTING %s\n%s' % (vm['hyperv_vm_name'], '----------'+'-'*len(vm['hyperv_vm_name'])))

		zone = None
		if 'cs_zone' in vm:
			zone = vm['cs_zone']
		elif conf.has_option('CLOUDSTACK', 'default_zone'):
			zone = conf.get('CLOUDSTACK', 'default_zone')

		domain = None
		if 'cs_domain' in vm:
			domain = vm['cs_domain']
		elif conf.has_option('CLOUDSTACK', 'default_domain'):
			domain = conf.get('CLOUDSTACK', 'default_domain')

		account = None
		if 'cs_account' in vm:
			account = vm['cs_account']
		elif conf.has_option('CLOUDSTACK', 'default_account'):
			account = conf.get('CLOUDSTACK', 'default_account')

		network = None
		if 'cs_network' in vm:
			network = vm['cs_network']
		elif conf.has_option('CLOUDSTACK', 'default_network'):
			network = conf.get('CLOUDSTACK', 'default_network')

		service_offering = None
		if 'cs_service_offering' in vm:
			service_offering = vm['cs_service_offering']
		elif conf.has_option('CLOUDSTACK', 'default_service_offering'):
			service_offering = conf.get('CLOUDSTACK', 'default_service_offering')


		# make sure we have a complete config before we start
		if zone and domain and account and network and service_offering:
			# manage the disks
			if 'disks' in vm and len(vm['disks']) > 0:
				# register the first disk as a template since it is the root disk
				print('Creating template for root volume %s...' % (vm['disks'][0]['name']))
				template = cs.request(dict({
					'command':'registerTemplate',
					'name':vm['disks'][0]['name'].replace(' ', '-'),
					'displaytext':vm['disks'][0]['name'],
					'format':'VHD',
					'hypervisor':'XenServer',
					'ostypeid':'138', # None
					'url':vm['disks'][0]['url'],
					'zoneid':zone,
					'domainid':domain,
					'account':account
				}))
				if template:
					print('Template created...')
				else:
					print('ERROR: Check the "%s" log for details' % (conf.get('CLOUDSTACK', 'log_file')))

				# check if there are data disks
				if len(vm['disks']) > 1:
					# upload the remaining disks as volumes
					for disk in vm['disks'][1:]:
						print('Uploading data volume %s...' % (disk['name']))
						volume = cs.request(dict({
							'command':'uploadVolume',
							'name':disk['name'].replace(' ', '-'),
							'format':'VHD',
							'url':disk['url'],
							'zoneid':zone,
							'domainid':domain,
							'account':account
						}))
						if volume:
							print('Volume uploaded...')
						else:
							print('ERROR: Check the "%s" log for details' % (conf.get('CLOUDSTACK', 'log_file')))
		else:
			print('We are missing settings fields for %s' % (vm['hyperv_vm_name']))



	### clean up the running.conf file...
	#os.remove('./running.conf')

