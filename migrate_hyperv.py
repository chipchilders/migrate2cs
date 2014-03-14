#!/usr/bin/env python

from ConfigParser import ConfigParser
from lib.hyperv import HyperV # the class
from lib.hyperv import hyperv # the connection
import json
import os
import pprint

# setup the conf object and set default values...
conf = ConfigParser()
conf.add_section('HYPERV')
conf.set('HYPERV', 'export_path', 'C:\RemoteExport')
conf.set('HYPERV', 'migrate_input', './migrate_hyperv_input.json')
conf.set('HYPERV', 'pscp_exe', 'C:\pscp.exe')

conf.add_section('WEBSERVER')
conf.set('WEBSERVER', 'host', '10.223.130.146')
conf.set('WEBSERVER', 'path', '/mnt/share/vhds')
conf.set('WEBSERVER', 'username', 'root')
conf.set('WEBSERVER', 'password', 'password')

# read in config files if they exists
conf.read(['./settings.conf', './running.conf'])

def copy_vhd_to_webserver(vhd_path):
	result, ok = hyperv.powershell('%s -l %s -pw %s %s %s:%s' % (
		conf.get('HYPERV', 'pscp_exe'),
		conf.get('WEBSERVER', 'username'),
		conf.get('WEBSERVER', 'password'),
		vhd_path,
		conf.get('WEBSERVER', 'host'),
		conf.get('WEBSERVER', 'path')
		))

if __name__ == "__main__":
	# comment out the following line to keep a history of the requests over multiple runs of this file.
	open(conf.get('HYPERV', 'log_file'), 'w').close() # cleans the powershell requests log before execution so it only includes this run.

	vm_input = []
	if os.path.exists(conf.get('HYPERV', 'migrate_input')):
		with open(conf.get('HYPERV', 'migrate_input'), 'r') as f:
			vm_input = json.load(f)

	vms = []
	if vm_input: # make sure there is data in the file
		for vm_in in vm_input: # loop through the vms in the file
			if 'hyperv_vm_name' in vm_in and 'hyperv_server' in vm_in: # make sure the minimum fields were entered
				objs, ok = hyperv.powershell('Get-VM -Name "%s" -Server "%s"' % (vm_in['hyperv_vm_name'], vm_in['hyperv_server']))
				if objs and ok: # make sure it found the specified VM
					vm_raw = objs[0]
					vm_out = {'name': vm_in['hyperv_vm_name']}
					
					# get cores
					cpu, ok = hyperv.powershell('Get-VMCPUCount -VM "%s" -Server "%s"' % (vm_in['hyperv_vm_name'], vm_in['hyperv_server']))
					if ok:
						vm_out['cores'] = int(cpu[0]['ProcessorsPerSocket']) * int(cpu[0]['SocketCount'])

					# get memory
					memory, ok = hyperv.powershell('Get-VMMemory -VM "%s" -Server "%s"' % (vm_in['hyperv_vm_name'], vm_in['hyperv_server']))
					if ok:
						vm_out['memory'] = int(memory[0]['Reservation'])

					# handle exporting running vms
					if int(vm_raw['EnabledState']) == HyperV.VM_RUNNING:
						vm_out['state'] = 'running'
						print('VM %s is Running' % (vm_in['hyperv_vm_name']))
						status, ok = hyperv.powershell('Stop-VM -VM "%s" -Server "%s" -Wait -Force' % (vm_in['hyperv_vm_name'], vm_in['hyperv_server']))
						if ok:
							print('Stopped %s' % (vm_out['name']))
							#export, ok = hyperv.powershell('Export-VM -VM "%s" -Server "%s" -Path "%s" -CopyState -Wait -Force' % 
							#	(vm_in['hyperv_vm_name'], vm_in['hyperv_server'], conf.get('HYPERV', 'export_path')))
							#if ok:
							#	print('Exported %s' % (vm_in['hyperv_vm_name']))
							#	status, ok = hyperv.powershell('Start-VM -VM "%s" -Server "%s" -Wait -Force' % (vm_in['hyperv_vm_name'], vm_in['hyperv_server']))
							#	if ok:
							#		print('Started %s' % (vm_in['hyperv_vm_name']))
					# handle exporting stopped vms
					elif int(vm_raw['EnabledState']) == HyperV.VM_STOPPED:
						vm_out['state'] = 'stopped'
						print('VM %s is Stopped' % (vm_in['hyperv_vm_name']))
						#export, ok = hyperv.powershell('Export-VM -VM "%s" -Server "%s" -Path "%s" -CopyState -Wait -Force' % 
						#	(vm_in['hyperv_vm_name'], vm_in['hyperv_server'], conf.get('HYPERV', 'export_path')))
						#if ok:
						#	print('Exported %s' % (vm_in['hyperv_vm_name']))
					else: # this should be improved...
						vm_out['state'] = 'unknown'
						print('VM %s is in an Unknown state' % (vm_in['hyperv_vm_name']))

					if (vm_out['state'] == 'running' and ok) or vm_out['state'] == 'stopped':
						disks, ok = hyperv.powershell('Get-VMDisk -VM "%s"' % (vm_in['hyperv_vm_name']))
						if ok:
							print disks



					vms.append(vm_out)

	print ""
	pprint.pprint(vms)


	### clean up the running.conf file...
	os.remove('./running.conf')

