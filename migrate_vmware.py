#!/usr/bin/env python

from ConfigParser import ConfigParser
from pysphere import VIServer
from lib.cloudstack import cs
from xml.etree import ElementTree as ET
import json
import logging
import os
import re
import subprocess
import sys
import time
if sys.version_info < (2, 7):
	import lib.legacy_subprocess
	subprocess.check_output = lib.legacy_subprocess.check_output

# setup the conf object and set default values...
conf = ConfigParser()
conf.add_section('VMWARE')
conf.set('VMWARE', 'log_file', './logs/vmware_api.log')

# read in config files if they exists
conf.read(['./settings.conf', './running.conf'])

if not conf.has_section('STATE'):
	conf.add_section('STATE') # STATE config section to maintain state of the running process
if not conf.has_option('STATE', 'migrate'):
	conf.set('STATE', 'migrate', '[]') # parsed with: json.loads(conf.get('STATE', 'migrate'))

conf.set('VMWARE', 'log_file', './logs/vmware_migration_%s.log' % (conf.get('STATE', 'migration_timestamp')))
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
	conf.read(['./running.conf'])
	vms = json.loads(conf.get('STATE', 'vms'))
	log.info('EXPORTING %s' % (vms[vm_id]['src_name']))
	vms[vm_id]['clean_name'] = re.sub('[^0-9a-zA-Z]+', '-', vms[vm_id]['src_name'])
	cmd = 'ovftool %s -tt=OVA -n=%s "vi://%s:%s@%s/%s/vm/%s" /mnt/share/vhds' % (
		'-o --powerOffSource --noSSLVerify --acceptAllEulas --skipManifestGeneration --noImageFiles',
		vms[vm_id]['clean_name'],
		conf.get('VMWARE', 'username').replace('@', '%40').replace('\\', '%5c').replace('!', '%21'),
		conf.get('VMWARE', 'password').replace('@', '%40').replace('\\', '%5c').replace('!', '%21'),
		conf.get('VMWARE', 'endpoint'),
		vms[vm_id]['src_dc'],
		vms[vm_id]['src_name']
	)
	output = ''
	try:
		#output = subprocess.check_output(cmd, shell=True)
		#log.info('Running the ovftool...\n%s' % (output))
		log.info('Running ovftool...')
		p = subprocess.Popen(cmd, stdout=subprocess.PIPE, bufsize=1, shell=True)
		for line in iter(p.stdout.readline, b''):
		    log.info(line)
		p.communicate() # close p.stdout, wait for the subprocess to exit
	except:
		log.info('Initial export attempt failed.  Trying a different export format...')
		# since the exports have been inconsistent, if the first fails, try this method.
		cmd = 'ovftool %s -tt=OVA -n=%s "vi://%s:%s@%s/%s?ds=%s" /mnt/share/vhds' % (
			'-o --powerOffSource --noSSLVerify --acceptAllEulas --skipManifestGeneration --noImageFiles',
			vms[vm_id]['clean_name'],
			conf.get('VMWARE', 'username').replace('@', '%40').replace('\\', '%5c').replace('!', '%21'),
			conf.get('VMWARE', 'password').replace('@', '%40').replace('\\', '%5c').replace('!', '%21'),
			conf.get('VMWARE', 'endpoint'),
			vms[vm_id]['src_dc'],
			vms[vm_id]['src_path'].replace(' ', '')
		)
		try:
			#output = subprocess.check_output(cmd, shell=True)
		#except subprocess.CalledProcessError, e:
			p = subprocess.Popen(cmd, stdout=subprocess.PIPE, bufsize=1, shell=True)
			for line in iter(p.stdout.readline, b''):
			    log.info(line)
			p.communicate() # close p.stdout, wait for the subprocess to exit
		except:
			log.error('Could not export %s \n%s' % (vms[vm_id]['src_name'], str(sys.exc_info())))
			conf.set('STATE', 'migrate_error', 'True')
	if not conf.getboolean('STATE', 'migrate_error'):
		# we have the resulting OVA file.  if there are multi disks, split them...
		split_ok = True
		if len(vms[vm_id]['src_disks']) > 1:
			log.info('Processing multi disk ova...')
			conf.set('STATE', 'vms', json.dumps(vms))
			with open('running.conf', 'wb') as f:
				conf.write(f) # update the file to include the changes we have made
			split_ok = split_ova(vm_id)
			if split_ok:
				conf.read(['./running.conf'])
				vms = json.loads(conf.get('STATE', 'vms'))
		elif len(vms[vm_id]['src_disks']) == 1:
			log.info('VM only has a root disk')
			vms[vm_id]['src_disks'][0]['ova'] = '%s.ova' % (vms[vm_id]['clean_name'])
			vms[vm_id]['src_disks'][0]['url'] = '%s://%s:%s%s%s' % (
							'https' if conf.get('FILESERVER', 'port') == '443' else 'http',
							conf.get('FILESERVER', 'host'),
							conf.get('FILESERVER', 'port'),
							conf.get('FILESERVER', 'base_uri'),
							'%s.ova' % (vms[vm_id]['clean_name']))
		if split_ok:
			log.info('Finished exporting %s' % (vms[vm_id]['src_name']))
			vms[vm_id]['state'] = 'exported'
		else:
			log.error('There were problems exporting the disks for %s' % (vms[vm_id]['src_name']))
		conf.set('STATE', 'vms', json.dumps(vms))
		with open('running.conf', 'wb') as f:
			conf.write(f) # update the file to include the changes we have made

def split_ova(vm_id):
	split_ok = True
	conf.read(['./running.conf'])
	vms = json.loads(conf.get('STATE', 'vms'))
	## this script is designed to work with Python 2.5+, so we are not using anything from ElementTree 1.3, only 1.2...
	## this is important in order to support CentOS.

	ns = {}
	ns['ns'] = 'http://schemas.dmtf.org/ovf/envelope/1'
	ns['ovf'] = 'http://schemas.dmtf.org/ovf/envelope/1'
	ns['cim'] = 'http://schemas.dmtf.org/wbem/wscim/1/common'
	ns['rasd'] = 'http://schemas.dmtf.org/wbem/wscim/1/cim-schema/2/CIM_ResourceAllocationSettingData'
	ns['vmw'] = 'http://www.vmware.com/schema/ovf'
	ns['vssd'] = 'http://schemas.dmtf.org/wbem/wscim/1/cim-schema/2/CIM_VirtualSystemSettingData'
	ns['xsi'] = 'http://www.w3.org/2001/XMLSchema-instance'

	ET._namespace_map[ns['ovf']] = 'ovf'
	ET._namespace_map[ns['cim']] = 'cim'
	ET._namespace_map[ns['rasd']] = 'rasd'
	ET._namespace_map[ns['vmw']] = 'vmw'
	ET._namespace_map[ns['vssd']] = 'vssd'
	ET._namespace_map[ns['xsi']] = 'xsi'

	DISK_RESOURCE_TYPE = 17

	src_ova_file = '%s.ova' % (vms[vm_id]['clean_name'])
	src_ova_base = vms[vm_id]['clean_name']
	cmd = 'cd %s; rm -rf %s; mkdir %s; tar xvf %s -C %s' % (
		conf.get('FILESERVER', 'files_path'), src_ova_base, src_ova_base, src_ova_file, src_ova_base)
	ret = subprocess.call(cmd, shell=True)

	if ret == 0:
		src_ovf_file = None
		for f in os.listdir('%s/%s' % (conf.get('FILESERVER', 'files_path'), src_ova_base)):
			if f.endswith('.ovf'):
				src_ovf_file = '%s/%s/%s' % (conf.get('FILESERVER', 'files_path'), src_ova_base, f)

		if src_ovf_file:
			src_dom = ET.parse(src_ovf_file)
			src_tree = src_dom.getroot()
			log.info('Splitting the ova file.  Creating an ova file for each disk...')

			for index in xrange(len(src_tree.findall('{%(ns)s}DiskSection/{%(ns)s}Disk' % ns))):
				dom = ET.parse(src_ovf_file)
				tree = dom.getroot()
				split_base = None

				# get the values we care about for this iteration
				disk_el = tree.findall('{%(ns)s}DiskSection/{%(ns)s}Disk' % ns)[index]
				disk_id = disk_el.attrib.get('{%(ovf)s}diskId' % ns, None)
				file_id = disk_el.attrib.get('{%(ovf)s}fileRef' % ns, None)
				file_nm = None
				for f in tree.findall('{%(ns)s}References/{%(ns)s}File' % ns):
					if f.attrib.get('{%(ovf)s}id' % ns, None) == file_id:
						file_nm = f.attrib.get('{%(ovf)s}href' % ns, None)
				split_base = os.path.splitext(file_nm)[0]

				# get the controller type
				controller_id = None
				controller_type = None
				for i in tree.findall('{%(ns)s}VirtualSystem/{%(ns)s}VirtualHardwareSection/{%(ns)s}Item' % ns):
					if int(i.find('{%(rasd)s}ResourceType' % ns).text) == DISK_RESOURCE_TYPE:
						if i.find('{%(rasd)s}HostResource' % ns).text.endswith(disk_id):
							controller_id = i.find('{%(rasd)s}Parent' % ns).text
				for i in tree.findall('{%(ns)s}VirtualSystem/{%(ns)s}VirtualHardwareSection/{%(ns)s}Item' % ns):
					if i.find('{%(rasd)s}InstanceID' % ns).text == controller_id:
						controller_type = i.find('{%(rasd)s}Description' % ns).text

				if 'IDE' in controller_type:
					log.info('Disk %s is using an IDE controller' % (split_base))
					log.warning('The IDE controller is not fully supported.  The VM will need to be manually verified to be working after the migration completes.')

				# loop through the different elements and remove the elements we don't want
				for d in tree.findall('{%(ns)s}DiskSection/{%(ns)s}Disk' % ns):
					if d.attrib.get('{%(ovf)s}diskId' % ns, None) != disk_id:
						parent = tree.find('{%(ns)s}DiskSection' % ns)
						parent.remove(d)
				for f in tree.findall('{%(ns)s}References/{%(ns)s}File' % ns):
					if f.attrib.get('{%(ovf)s}id' % ns, None) != file_id:
						parent = tree.find('{%(ns)s}References' % ns)
						parent.remove(f)
				for i in tree.findall('{%(ns)s}VirtualSystem/{%(ns)s}VirtualHardwareSection/{%(ns)s}Item' % ns):
					if int(i.find('{%(rasd)s}ResourceType' % ns).text) == DISK_RESOURCE_TYPE:
						if not i.find('{%(rasd)s}HostResource' % ns).text.endswith(disk_id):
							parent = tree.find('{%(ns)s}VirtualSystem/{%(ns)s}VirtualHardwareSection' % ns)
							parent.remove(i)

				# update elements that require specific values
				for c in tree.findall('{%(ns)s}VirtualSystem/{%(ns)s}VirtualHardwareSection/{%(vmw)s}Config' % ns):
					if c.attrib.get('{%(vmw)s}key' % ns, None) == 'tools.toolsUpgradePolicy':
						c.set('{%(vmw)s}value' % ns, 'manual')
				
				split_ofv_file = '%s/%s/%s.ovf' % (conf.get('FILESERVER', 'files_path'), src_ova_base, split_base)
				with open(split_ofv_file, 'w') as f:
					f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
					dom.write(f, encoding='utf-8')

				## since the '' and 'ovf' namespaces have the same url, we have to keep the 'ovf' on attributes, but not on tags.
				cmd = "perl -pi -e 's,<ovf:,<,g' %s" % (split_ofv_file)
				ret = subprocess.call(cmd, shell=True)
				cmd = "perl -pi -e 's,</ovf:,</,g' %s" % (split_ofv_file)
				ret = subprocess.call(cmd, shell=True)

				## apparently the namespaces need to be exactly as specified and can't be re-saved.  replace the Envelope.  no id passed...
				ns_str = ''
				for k, v in ns.items():
					if k == 'ns':
						ns_str = '%s xmlns="%s"' % (ns_str, v)
					else:
						ns_str = '%s xmlns:%s="%s"' % (ns_str, k, v)
				cmd = "perl -pi -e 's,<Envelope.*>,%s,g' %s" % (
					'<Envelope%s>' % (ns_str),
					split_ofv_file)
				ret = subprocess.call(cmd, shell=True)

				cmd = 'cd %s/%s; rm -rf ../%s.ova; tar cvf ../%s.ova %s.ovf %s' % (
					conf.get('FILESERVER', 'files_path'), src_ova_base, split_base, split_base, split_base, file_nm)
				ret = subprocess.call(cmd, shell=True)
				if ret == 0:
					log.info('Created %s.ova' % (split_base))
					if len(vms[vm_id]['src_disks']) > index:
						vms[vm_id]['src_disks'][index]['ova'] = '%s.ova' % (split_base)
						vms[vm_id]['src_disks'][index]['url'] = '%s://%s:%s%s%s' % (
							'https' if conf.get('FILESERVER', 'port') == '443' else 'http',
							conf.get('FILESERVER', 'host'),
							conf.get('FILESERVER', 'port'),
							conf.get('FILESERVER', 'base_uri'),
							'%s.ova' % (split_base))
						conf.set('STATE', 'vms', json.dumps(vms))
						with open('running.conf', 'wb') as f:
							conf.write(f) # update the file to include the changes we have made
					else:
						log.error('Could not save the ova to the vms disk due to index out of bound')
						split_ok = False
				else:
					log.error('Failed to create %s.ova' % (split_base))
					split_ok = False
		else:
			log.error('Failed to locate the source ovf file %s/%s/%s.ovf' % (
				conf.get('FILESERVER', 'files_path'), src_ova_base, src_ova_base))
			split_ok = False
		# remove the directory we used to create the new OVA files
		cmd = 'cd %s; rm -rf %s' % (conf.get('FILESERVER', 'files_path'), src_ova_base)
		ret = subprocess.call(cmd, shell=True)
		if ret == 0:
			log.info('Successfully removed temporary disk files')
		else:
			log.warning('Failed to remove temporary disk files.  Consider cleaning up the directory "%s" after the migration.' % (
				conf.get('FILESERVER', 'files_path')))
	else:
		log.error('Failed to extract the ova file %s/%s' % (conf.get('FILESERVER', 'files_path'), src_ova_file))
		split_ok = False
	return split_ok


def import_vm(vm_id):
	# import the vm
	conf.read(['./running.conf'])
	vms = json.loads(conf.get('STATE', 'vms'))
	log.info('IMPORTING %s' % (vms[vm_id]['src_name']))
	if vms[vm_id]['src_name'] != vms[vm_id]['clean_name']:
		log.info('Renaming VM from %s to %s to comply with CloudPlatform...' % (vms[vm_id]['src_name'], vms[vm_id]['clean_name']))
	imported = False

	# make sure we have a complete config before we start
	if ('cs_zone' in vms[vm_id] and 'cs_domain' in vms[vm_id] and 'cs_account' in vms[vm_id] and 'cs_service_offering' in vms[vm_id]):
		# manage the disks
		if len(vms[vm_id]['src_disks']) > 0:
			# get the possible os type ids
			os_type = ''
			type_search = 'Other (64-bit)'
			if vms[vm_id]['src_os_arch'] == 32:
				type_search = 'Other (32-bit)'
			type_ids = cs.request(dict({'command':'listOsTypes'}))
			if type_ids and 'ostype' in type_ids:
				for os_type_obj in type_ids['ostype']:
					if os_type_obj['description'] == type_search:
						os_type = os_type_obj['id']
						break

			# register the first disk as a template since it is the root disk
			root_name = os.path.splitext(vms[vm_id]['src_disks'][0]['ova'])[0]
			log.info('Creating template for root volume %s...' % (root_name))
			template = cs.request(dict({
				'command':'registerTemplate',
				'name':root_name,
				'displaytext':root_name,
				'format':'OVA',
				'hypervisor':'VMware',
				'ostypeid':os_type,
				'url':vms[vm_id]['src_disks'][0]['url'],
				'zoneid':vms[vm_id]['cs_zone'],
				'domainid':vms[vm_id]['cs_domain'],
				'account':vms[vm_id]['cs_account']
			}))
			if template:
				log.info('Template %s created' % (template['template'][0]['id']))
				vms[vm_id]['cs_template_id'] = template['template'][0]['id']
				imported = True
			else:
				log.error('Failed to create template.  Check the "%s" log for details.' % (conf.get('CLOUDSTACK', 'log_file')))

			# check if there are data disks
			if len(vms[vm_id]['src_disks']) > 1:
				# upload the remaining disks as volumes
				for i,v in enumerate(vms[vm_id]['src_disks'][1:]):
					index = i+1
					imported = False # reset because we have more to do...
					disk_name = os.path.splitext(vms[vm_id]['src_disks'][index]['ova'])[0]
					log.info('Uploading data volume %s...' % (disk_name))
					volume = cs.request(dict({
						'command':'uploadVolume',
						'name':disk_name,
						'format':'OVA',
						'url':vms[vm_id]['src_disks'][index]['url'],
						'zoneid':vms[vm_id]['cs_zone'],
						'domainid':vms[vm_id]['cs_domain'],
						'account':vms[vm_id]['cs_account']
					}))
					if volume and 'jobresult' in volume and 'volume' in volume['jobresult']:
						volume_id = volume['jobresult']['volume']['id']
						log.info('Volume %s uploaded' % (volume_id))
						if 'cs_volumes' in vms[vm_id]:
							vms[vm_id]['cs_volumes'].append(volume_id)
						else:
							vms[vm_id]['cs_volumes'] = [volume_id]
						imported = True
					else:
						log.error('Failed to upload the volume.  Check the "%s" log for details.' % (conf.get('CLOUDSTACK', 'log_file')))
	else:
		log.error('We are missing CCP data for %s' % (vms[vm_id]['src_name']))

	if imported:
		### Update the running.conf file
		log.info('Finished importing %s' % (vms[vm_id]['clean_name']))
		vms[vm_id]['state'] = 'imported'
		conf.set('STATE', 'vms', json.dumps(vms))
		with open('running.conf', 'wb') as f:
			conf.write(f) # update the file to include the changes we have made

def launch_vm(vm_id):
	# launch the new vm
	conf.read(['./running.conf'])
	vms = json.loads(conf.get('STATE', 'vms'))
	log.info('LAUNCHING %s' % (vms[vm_id]['clean_name']))

	poll = 1
	has_error = False
	while not has_error and vms[vm_id]['state'] != 'launched':
		# check if the template has finished downloading...
		template = cs.request(dict({
			'command':'listTemplates', 
			'listall':'true', 
			'templatefilter':'self', 
			'id':vms[vm_id]['cs_template_id']
		}))
		if template and 'template' in template and len(template['template']) > 0:
			if template['template'][0]['isready']: # template is ready
				volumes_ready = True
				if 'cs_volumes' in vms[vm_id] and len(vms[vm_id]['cs_volumes']) > 0: # check if volumes are ready
					for volume_id in vms[vm_id]['cs_volumes']:
						volume = cs.request(dict({
							'command':'listVolumes', 
							'listall':'true', 
							'id':volume_id
						}))
						if volume and 'volume' in volume and len(volume['volume']) > 0:
							# check the state of the volume
							if volume['volume'][0]['state'] != 'Uploaded' and volume['volume'][0]['state'] != 'Ready':
								log.info('%s: %s is waiting for volume %s, current state: %s' % 
									(poll, vms[vm_id]['clean_name'], volume['volume'][0]['name'], volume['volume'][0]['state']))
								volumes_ready = False
							else:
								volumes_ready = volumes_ready and True # propogates False if any are False
				# everything should be ready for this VM to be started, go ahead...
				if volumes_ready:
					log.info('%s: %s is ready to launch' % (poll, vms[vm_id]['clean_name']))
					log.info('Launching VM %s...' % (vms[vm_id]['clean_name']))
					# create a VM instance using the template
					cmd = dict({
						'command':'deployVirtualMachine',
						'name':vms[vm_id]['clean_name'],
						'displayname':vms[vm_id]['clean_name'],
						'templateid':vms[vm_id]['cs_template_id'],
						'serviceofferingid':vms[vm_id]['cs_service_offering'],
						'zoneid':vms[vm_id]['cs_zone'],
						'domainid':vms[vm_id]['cs_domain'],
						'account':vms[vm_id]['cs_account']
					})
					if 'cs_network' in vms[vm_id] and vms[vm_id]['cs_network'] != '': # pass in a network if it is available
						cmd['networkids'] = vms[vm_id]['cs_network']
					cs_vm = cs.request(cmd) # launch the VM
					if cs_vm and 'jobresult' in cs_vm and 'virtualmachine' in cs_vm['jobresult']:
						log.info('VM %s launched' % (vms[vm_id]['clean_name']))

						# attach the data volumes to it if there are data volumes
						if 'cs_volumes' in vms[vm_id] and len(vms[vm_id]['cs_volumes']) > 0:
							for volume_id in vms[vm_id]['cs_volumes']:
								log.info('Attaching volume %s...' % (volume_id))
								attach = cs.request(dict({
									'command':'attachVolume',
									'id':volume_id,
									'virtualmachineid':cs_vm['jobresult']['virtualmachine']['id']}))
								if attach and 'jobstatus' in attach and attach['jobstatus']:
									log.info('Successfully attached volume %s' % (volume_id))
								else:
									log.error('Failed to attach volume %s' % (volume_id))
									has_error = True
							if not has_error:
								log.info('Rebooting the VM to make the attached volumes visible...')
								reboot = cs.request(dict({
									'command':'rebootVirtualMachine', 
									'id':cs_vm['jobresult']['virtualmachine']['id']}))
								if reboot and 'jobstatus' in reboot and reboot['jobstatus']:
									log.info('VM rebooted')
								else:
									log.error('VM did not reboot.  Check the VM to make sure it came up correctly.')
						if not has_error:
							### Update the running.conf file
							conf.read(['./running.conf']) # make sure we have everything from this file already
							vms[vm_id]['cs_vm_id'] = cs_vm['jobresult']['virtualmachine']['id']
							vms[vm_id]['state'] = 'launched'
							conf.set('STATE', 'vms', json.dumps(vms))
							with open('running.conf', 'wb') as f:
								conf.write(f) # update the file to include the changes we have made
					elif cs_vm and 'jobresult' in cs_vm and 'errortext' in cs_vm['jobresult']:
						log.error('%s failed to start!  ERROR: %s' % (vms[vm_id]['clean_name'], cs_vm['jobresult']['errortext']))
						has_error = True
					else:
						log.error('%s did not Start or Error correctly...' % (vms[vm_id]['clean_name']))
						has_error = True
			else:
				log.info('%s: %s is waiting for template, current state: %s'% (poll, vms[vm_id]['clean_name'], template['template'][0]['status']))
		if vms[vm_id]['state'] != 'launched':
			log.info('... polling ...')
			poll = poll + 1
			time.sleep(10)
	if not has_error: # complete the migration...
		conf.read(['./running.conf'])
		vms = json.loads(conf.get('STATE', 'vms'))

		# clean up ova files
		cmd = 'cd %s; rm -f %s.ova %s-disk*' % (conf.get('FILESERVER', 'files_path'), vms[vm_id]['clean_name'], vms[vm_id]['clean_name'])
		ret = subprocess.call(cmd, shell=True)
		if ret == 0:
			log.info('Successfully removed the imported OVA files from the file server')
		else:
			log.warning('Failed to remove the imported OVA files.  Consider cleaning up the directory "%s" after the migration.' % (
				conf.get('FILESERVER', 'files_path')))

		# save the updated state
		vms[vm_id]['state'] = 'migrated'
		conf.set('STATE', 'vms', json.dumps(vms))
		migrate = json.loads(conf.get('STATE', 'migrate'))
		migrate.remove(vm_id)
		conf.set('STATE', 'migrate', json.dumps(migrate))
		with open('running.conf', 'wb') as f:
			conf.write(f) # update the file to include the changes we have made
		log.info('SUCCESSFULLY MIGRATED %s to %s' % (vms[vm_id]['src_name'], vms[vm_id]['clean_name']))

# run the actual migration
def do_migration():
	conf.read(['./running.conf'])
	vms = json.loads(conf.get('STATE', 'vms'))
	migrate = json.loads(conf.get('STATE', 'migrate'))
	for vm_id in migrate[:]: # makes a copy of the list so we can delete from the original
		state = vms[vm_id]['state']
		if state == '' or state == 'migrated':
			export_vm(vm_id)
			import_vm(vm_id)
			launch_vm(vm_id)
		elif state == 'exported':
			import_vm(vm_id)
			launch_vm(vm_id)
		elif state == 'imported':
			launch_vm(vm_id)
		elif state == 'launched':
			conf.read(['./running.conf'])
			vms = json.loads(conf.get('STATE', 'vms'))
			vms[vm_id]['state'] = 'migrated'
			conf.set('STATE', 'vms', json.dumps(vms))
			migrate.remove(vm_id)
			conf.set('STATE', 'migrate', json.dumps(migrate))
			with open('running.conf', 'wb') as f:
				conf.write(f) # update the file to include the changes we have made


if __name__ == "__main__":
	do_migration()
	if conf.getboolean('STATE', 'migrate_error'):
		log.info('Finished with ERRORS!!!\n')
	else:
		log.info('ALL FINISHED!!!\n')

	log.info('~~~ ~~~ ~~~ ~~~')

	# cleanup settings that need to be refereshed each run
	conf.remove_option('STATE', 'migrate_error')

