#!/usr/bin/env python

## Copyright (c) 2014 Citrix Systems, Inc. All Rights Reserved.
## You may only reproduce, distribute, perform, display, or prepare derivative works of this file pursuant to a valid license from Citrix.

from lib.hyperv import HyperV # the class
from lib.hyperv import hyperv # the connection
import lib.cloudstack
# from lib.cloudstack import cs
import json
import hashlib
import ntpath
import os
import pprint
import sys
import time
import lib.config_manager
from lib.config_manager import ConfigManager
import common_services

class HypverMigrator:

	def __init__(self, confMgr):
		HYPERVISOR_TYPE = 'hyperv'
		defaultHypervConfig =[
		('HYPERVISOR', 'hypervisorType', HYPERVISOR_TYPE),
		('HYPERVISOR', 'migration_input_file', './input/migrate_hyperv_input.json'), 
		('HYPERVISOR', 'pscp_exe', 'C:\pscp.exe'),
		('HYPERVISOR', 'log_file', './logs/hyperv_api.log'),
		('STATE', 'active_migration', 'False'),
		('STATE', 'exported', '[]'),
		('STATE', 'imported', '[]'),
		('STATE', 'started', '[]'),
		('STATE', 'foo', 'bar'),
		('STATE', 'started', '[]'),
		]

		self.confMgr = confMgr
		if not self.confMgr:
			configFile = './settings-' + HYPERVISOR_TYPE + '.conf'
			persistentStore = './running-'+HYPERVISOR_TYPE+'.conf'
			self.confMgr = ConfigManager(configFile, persistentStore, defaultHypervConfig)

		self.confMgr.addOptionsToSection('CLOUDSTACK', lib.cloudstack.getCloudStackConfig()) #let's put all the running configs in the same persistent store
		log = common_services.createMigrationLog(self.confMgr)

	def updateVms(self, vms):
		self.confMgr.updateOptions([('STATE', 'vms', vms)], True)


	def get_vm_info(self, vm_id, vm_in):
		# make sure the minimum fields were entered and they have not been processed already
		if 'hyperv_vm_name' in vm_in and 'hyperv_server' in vm_in and vm_id not in json.loads(self.confMgr.get('STATE', 'exported')):
			objs, ok = hyperv.powershell('Get-VM -Name "%s" -Server "%s"' % (vm_in['hyperv_vm_name'], vm_in['hyperv_server']))
			if objs and ok: # make sure it found the specified VM
				print('\nGETTING VM INFO %s\n%s' % (vm_in['hyperv_vm_name'], '----------'+'-'*len(vm_in['hyperv_vm_name'])))

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
					print('ERROR: Check the "%s" log for details' % (self.confMgr.get('HYPERVISOR', 'log_file')))

				# get memory
				memory, ok = hyperv.powershell('Get-VMMemory -VM "%s" -Server "%s"' % (vm_in['hyperv_vm_name'], vm_in['hyperv_server']))
				if ok:
					vm_out['src_memory'] = int(memory[0]['Reservation'])
				else:
					print('Get-VMMemory powershell command failed on %s' % (vm_in['hyperv_vm_name']))
					print('ERROR: Check the "%s" log for details' % (self.confMgr.get('HYPERVISOR', 'log_file')))

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
										'https' if self.confMgr.get('FILESERVER', 'port') == '443' else 'http',
										self.confMgr.get('FILESERVER', 'host'),
										self.confMgr.get('FILESERVER', 'port'),
										self.confMgr.get('FILESERVER', 'base_uri'),
										ntpath.split(disk['DiskImage'])[1].replace(' ', '-')
										)
									})
					else:
						print('Get-VMDisk powershell command failed on %s' % (vm_in['hyperv_vm_name']))
						print('ERROR: Check the "%s" log for details' % (self.confMgr.get('HYPERVISOR', 'log_file')))
		return vm_out



	def discover_vms(self):
		self.confMgr.refresh()
		if self.confMgr.has_option('STATE', 'vms'):
			# initialize the 'vms' variable from the existing config...
			vms = json.loads(self.confMgr.get('STATE', 'vms'))
		else:
			vms = {}

		if self.confMgr.has_option('STATE', 'vm_order'):
			order = json.loads(self.confMgr.get('STATE', 'vm_order'))
		else:
			order = []

		with open(self.confMgr.get('HYPERVISOR', 'log_file'), 'a') as f:
			f.write('\n\nDISCOVERING HYPERV...\n')

		discovered = [] # vms of this discovery.  we will remove the vm's from 'vms' later if they are not in this array.

		vm_input = {}
		if os.path.exists(self.confMgr.get('HYPERVISOR', 'migration_input_file')):
			with open(self.confMgr.get('HYPERVISOR', 'migration_input_file'), 'r') as f:
				try:
					vm_input = json.load(f)
				except:
					print sys.exc_info()
					sys.exit("Error in the formatting of '%s'" % (self.confMgr.get('HYPERVISOR', 'migration_input_file')))

		print('\n-----------------------\n-- discovering vms... --\n-----------------------')
		# collect data about the VMs from HyperV and populate a list of VMs

		if vm_input: # make sure there is data in the file
			for vm_key in vm_input: # loop through the vms in the file
				vm_in = vm_input[vm_key]
				pprint.pprint(vm_in)
				vm_id = hashlib.sha1(vm_in['hyperv_server']+"|"+vm_in['hyperv_vm_name']).hexdigest()
				if vm_id not in order:
					order.append(vm_id)
				if vm_id not in vms:
					vms[vm_id] = {}

				vms[vm_id] = self.get_vm_info(vm_id, vm_in)
				discovered.append(vm_id)
						
		# loop through the 'vms' and remove any that were not discovered in this pass...
		for vm_id in vms.keys():
			if vm_id not in discovered:
				del vms[vm_id] # no longer a valid VM, so remove it...
				if vm_id in order: # remove the vm from the order list as well if it exists...
					order.remove(vm_id)

		### Update the running-hyperv.conf file
		self.confMgr.updateOptions([('STATE', 'vms', vms), ('STATE', 'vm_order', order)], True)
		self.confMgr.updateRunningConfig()

		return vms, order


	# copy vhd files to the file server
	def copy_vhd_to_file_server(self, vhd_path, vhd_name):
		return hyperv.powershell('%s -l %s -pw %s "%s" %s:%s/%s' % (
			self.confMgr.get('HYPERVISOR', 'pscp_exe'),
			self.confMgr.get('FILESERVER', 'username'),
			self.confMgr.get('FILESERVER', 'password'),
			vhd_path,
			self.confMgr.get('FILESERVER', 'host'),
			self.confMgr.get('FILESERVER', 'files_path'),
			vhd_name
		))


	def export_one_vm(self, vm_id):
		print('\n-----------------------\n-- RUNNING VM EXPORT --\n-----------------------')
		self.confMgr.refresh()
		if not self.confMgr.getboolean('STATE', 'migrate_error'):
			# initialize the 'vms' variable from the existing config...
			vms = json.loads(self.confMgr.get('STATE', 'vms'))
			log.info('EXPORTING %s' % (vms[vm_id]['src_name']))
				# make sure the minimum fields were entered and they have not been processed already

			if (vms[vm_id]['state'] == 'running' and ok) or vms[vm_id]['state'] == 'stopped':
				for disk in disks:
					if 'DriveName' in disk and disk['DriveName'] == 'Hard Drive' and 'DiskImage' in disk:
						print('Copying drive %s' % (disk['DiskImage']))
						exported = True
						result, ok = self.copy_vhd_to_file_server(disk['DiskImage'], ntpath.split(disk['DiskImage'])[1].replace(' ', '-'))
						if ok:
							print('Finished copy...')
							exported = True
						else:
							print('Copy failed...')
							print('ERROR: Check the "%s" log for details' % (self.confMgr.get('HYPERVISOR', 'log_file')))

			# bring the machines back up that were running now that we copied their disks
			if vms[vm_id]['state'] == 'running':
				status, ok = hyperv.powershell('Start-VM -VM "%s" -Server "%s" -Wait -Force' % (vm_in['hyperv_vm_name'], vm_in['hyperv_server']))
				if ok:
					print('Re-Started VM %s' % (vm_in['hyperv_vm_name']))
				else:
					print('Failed to restart the server.')
					print('ERROR: Check the "%s" log for details' % (self.confMgr.get('HYPERVISOR', 'log_file')))

			print('Finished exporting %s' % (vm_in['hyperv_vm_name']))

			if exported:
				### Update the running-hyperv.conf file
				self.confMgr.refresh()
				exported = json.loads(self.confMgr.get('STATE', 'exported'))
				exported.append(vms[vm_id]['id'])
				self.confMgr.updateOptions([('STATE', 'exported', exported)])
				self.updateVms(vms)
				self.confMgr.updateRunningConfig()

		print "\nCurrent VM Objects:"
		pprint.pprint(vms[vm_id])

	def import_vm(self, vm_id):
		print('\n\n-----------------------\n-- RUNNING VM IMPORT --\n-----------------------')
		# go through the VMs and import them into CS
		for i, vm in enumerate(vms):
			vm_id = hashlib.sha1(vm['hyperv_server']+"|"+vm['hyperv_vm_name']).hexdigest()
			if vm_id not in json.loads(self.confMgr.get('STATE', 'imported')):
				print('\nIMPORTING %s\n%s' % (vm['hyperv_vm_name'], '----------'+'-'*len(vm['hyperv_vm_name'])))
				imported = False

				## setup the cloudstack details we know (or are using defaults for)
				if 'cs_zone' not in vm and self.confMgr.has_option('CLOUDSTACK', 'default_zone'):
					vm['cs_zone'] = self.confMgr.get('CLOUDSTACK', 'default_zone')
					zone = cs.request(dict({'command':'listZones', 'id':vm['cs_zone']}))
					if zone and 'zone' in zone and len(zone['zone']) > 0:
						if zone['zone'][0]['networktype'] == 'Basic':
							vm['cs_zone_network'] = 'basic'
						else:
							vm['cs_zone_network'] = 'advanced'

				if 'cs_domain' not in vm and self.confMgr.has_option('CLOUDSTACK', 'default_domain'):
					vm['cs_domain'] = self.confMgr.get('CLOUDSTACK', 'default_domain')

				if 'cs_account' not in vm and self.confMgr.has_option('CLOUDSTACK', 'default_account'):
					vm['cs_account'] = self.confMgr.get('CLOUDSTACK', 'default_account')

				if 'cs_network' not in vm and self.confMgr.has_option('CLOUDSTACK', 'default_network'):
					vm['cs_network'] = self.confMgr.get('CLOUDSTACK', 'default_network')

				if 'cs_additional_networks' not in vm and self.confMgr.has_option('CLOUDSTACK', 'additional_networks'):
					vm['cs_additional_networks'] = self.confMgr.get('CLOUDSTACK', 'additional_networks')

				if 'cs_service_offering' not in vm and self.confMgr.has_option('CLOUDSTACK', 'default_service_offering'):
					vm['cs_service_offering'] = self.confMgr.get('CLOUDSTACK', 'default_service_offering')


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
							print('ERROR: Check the "%s" log for details' % (self.confMgr.get('CLOUDSTACK', 'log_file')))

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
									print('ERROR: Check the "%s" log for details' % (self.confMgr.get('CLOUDSTACK', 'log_file')))
				else:
					print('We are missing settings fields for %s' % (vm['hyperv_vm_name']))

				if imported:
					### Update the running-hyperv.conf file
					self.confMgr.refresh()
					imported = json.loads(self.confMgr.get('STATE', 'imported'))
					imported.append(vm['id'])
					self.confMgr.updateOptions([('STATE', 'imported', imported)])
					self.updateVms(vms)
					self.confMgr.updateRunningConfig()

	# run the actual migration
	def launch_vm(self, vm_id):
		print('\n\n----------------------------\n-- LAUNCHING IMPORTED VMS --\n----------------------------')
		# go through the imported VMs and start them and attach their volumes if they have any
		poll = 1
		has_error = False
		while len(json.loads(self.confMgr.get('STATE', 'started'))) != len(json.loads(self.confMgr.get('STATE', 'imported'))) and not has_error:
			for i, vm in enumerate(vms):
				vm_id = hashlib.sha1(vm['hyperv_server']+"|"+vm['hyperv_vm_name']).hexdigest()
				isAVm = 'cs_service_offering' in vm
				print("__________%s is a vm: %s________________________" % (vm_id, isAVm))
				if vm_id not in json.loads(self.confMgr.get('STATE', 'started')) and 'cs_service_offering' in vm:
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
									### Update the running-hyperv.conf file
									self.confMgr.refresh()
									started = json.loads(self.confMgr.get('STATE', 'started'))
									started.append(vm['id'])
									self.confMgr.updateOptions([('STATE', 'started', started)])
									self.updateVms(vms)
									self.confMgr.updateRunningConfig()

									# attach the data volumes to it if there are data volumes
									if 'cs_volumes' in vm and len(vm['cs_volumes']) > 0:
										for volume_id in vm['cs_volumes']:
											print('Attaching vol:%s to vm:%s ...' % (volume_id, cs_vm['jobresult']['virtualmachine']['id']))
											attach = cs.request(dict({
											'id':volume_id,
											'command':'attachVolume',
											'virtualmachineid':cs_vm['jobresult']['virtualmachine']['id']
											}))


											if attach and 'jobstatus' in attach and attach['jobstatus']:
												print('Successfully attached volume %s' % (volume_id))
											else:
												print('Failed to attach volume %s' % (volume_id))
												has_error = True
												self.confMgr.refresh()
												self.confMgr.updateOptions([('STATE', 'migrate_error', 'True')])
												self.updateVms(vms)
												self.confMgr.updateRunningConfig()
										if not has_error:
											print('Rebooting the VM to make the attached volumes visible...')
											reboot = cs.request(dict({
												'command':'rebootVirtualMachine', 
												'id':cs_vm['jobresult']['virtualmachine']['id']}))
											if reboot and 'jobstatus' in reboot and reboot['jobstatus']:
												print('VM rebooted')
											else:
												print('VM did not reboot.  Check the VM to make sure it came up correctly.')
									if not has_error:
										### Update the running-hyperv.conf file
										self.confMgr.refresh() # make sure we have everything from this file already
										vms[i]['cs_vm_id'] = cs_vm['jobresult']['virtualmachine']['id']
										vms[i]['state'] = 'launched'
										self.updateVms(vms)
										self.confMgr.updateRunningConfig()

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

		### clean up the running-hyperv.conf file...
		#os.remove('./running-hyperv.conf')


	# run the actual migration
	def do_migration(self):
		self.confMgr.refresh()
		vms = json.loads(self.confMgr.get('STATE', 'vms'))
		migrate = json.loads(self.confMgr.get('STATE', 'migrate'))
		for vm_id in migrate[:]: # makes a copy of the list so we can delete from the original
			if self.confMgr.getboolean('STATE', 'migrate_error'):
				break
			state = vms[vm_id]['state']
			if state == '' or state == 'migrated':
				self.export_vm(vm_id)
				self.import_vm(vm_id)
				self.launch_vm(vm_id)
			elif state == 'exported':
				self.import_vm(vm_id)
				self.launch_vm(vm_id)
			elif state == 'imported':
				self.launch_vm(vm_id)
			elif state == 'launched':
				self.confMgr.refresh()
				vms = json.loads(self.confMgr.get('STATE', 'vms'))
				vms[vm_id]['state'] = 'migrated'
				migrate.remove(vm_id)
				self.confMgr.updateOptions([('STATE', 'vms', vms), ('STATE', 'migrate', migrate)], True)
				self.confMgr.updateRunningConfig()

if __name__ == "__main__":
	hypverMigrator = HypverMigrator(None)
	hypverMigrator.do_migration()
	print('\n\nALL FINISHED!!!\n\n')

