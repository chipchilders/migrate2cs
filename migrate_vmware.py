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
		output = subprocess.check_output(cmd, shell=True)
		log.info('Running the ovftool...\n%s' % (output))
	except subprocess.CalledProcessError, e:
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
			output = subprocess.check_output(cmd, shell=True)
		except subprocess.CalledProcessError, e:
			log.error('Could not export %s... \n%s' % (vms[vm_id]['src_name'], e.output))
			conf.set('STATE', 'migrate_error', 'True')
	if not conf.getboolean('STATE', 'migrate_error'):
		# we have the resulting OVA file.  if there are multi disks, split them...
		split_ok = True
		if len(vms[vm_id]['src_disks']) > 1:
			conf.set('STATE', 'vms', json.dumps(vms))
			with open('running.conf', 'wb') as f:
				conf.write(f) # update the file to include the changes we have made
			split_ok = split_ova(vm_id)
			if split_ok:
				conf.read(['./running.conf'])
				vms = json.loads(conf.get('STATE', 'vms'))
		elif len(vms[vm_id]['src_disks']) == 1:
			vms[vm_id]['src_disks'][0]['ova'] = '%s.ova' % (vms[vm_id]['clean_name'])

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
		conf.get('FILESERVER', 'nfs_mount'), src_ova_base, src_ova_base, src_ova_file, src_ova_base)
	ret = subprocess.call(cmd, shell=True)

	if ret == 0:
		src_ovf_file = None
		for f in os.listdir('%s/%s' % (conf.get('FILESERVER', 'nfs_mount'), src_ova_base)):
			if f.endswith('.ovf'):
				src_ovf_file = '%s/%s/%s' % (conf.get('FILESERVER', 'nfs_mount'), src_ova_base, f)

		if src_ovf_file:
			src_dom = ET.parse(src_ovf_file)
			src_tree = src_dom.getroot()

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
				
				split_ofv_file = '%s/%s/%s.ovf' % (conf.get('FILESERVER', 'nfs_mount'), src_ova_base, split_base)
				with open(split_ofv_file, 'w') as f:
					f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
					dom.write(f, encoding='utf-8')

				## since the '' and 'ovf' namespaces have the same url, we have to keep the 'ovf' on attributes, but not on tags.
				cmd = "perl -pi -e 's,<ovf:,<,g' %s" % (split_ofv_file)
				ret = subprocess.call(cmd, shell=True)
				cmd = "perl -pi -e 's,</ovf:,</,g' %s" % (split_ofv_file)
				ret = subprocess.call(cmd, shell=True)

				## apparently the namespaces need to be exactly as specified and can't be re-saved.  replace the Envelope.  no id passed...
				cmd = "perl -pi -e 's,<Envelope.*>,%s,g' %s" % (
					'<Envelope xmlns="http://schemas.dmtf.org/ovf/envelope/1" xmlns:cim="http://schemas.dmtf.org/wbem/wscim/1/common" xmlns:ovf="http://schemas.dmtf.org/ovf/envelope/1" xmlns:rasd="http://schemas.dmtf.org/wbem/wscim/1/cim-schema/2/CIM_ResourceAllocationSettingData" xmlns:vmw="http://www.vmware.com/schema/ovf" xmlns:vssd="http://schemas.dmtf.org/wbem/wscim/1/cim-schema/2/CIM_VirtualSystemSettingData" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">',
					split_ofv_file)
				ret = subprocess.call(cmd, shell=True)

				cmd = 'cd %s/%s; rm -rf ../%s.ova; tar cvf ../%s.ova %s.ovf %s' % (
					conf.get('FILESERVER', 'nfs_mount'), src_ova_base, split_base, split_base, split_base, file_nm)
				ret = subprocess.call(cmd, shell=True)
				if ret == 0:
					log.info('created %s.ova' % (split_base))
					if len(vms[vm_id]['src_disks']) > index:
						vms[vm_id]['src_disks'][index]['ova'] = '%s.ova' % (split_base)
						conf.set('STATE', 'vms', json.dumps(vms))
						with open('running.conf', 'wb') as f:
							conf.write(f) # update the file to include the changes we have made
					else:
						log.error('could not save the ova to the vms disk due to index out of bound')
						split_ok = False
				else:
					log.error('failed to create %s.ova' % (split_base))
					split_ok = False
		else:
			log.error('failed to locate the source ovf file %s/%s/%s.ovf' % (
				conf.get('FILESERVER', 'nfs_mount'), src_ova_base, src_ova_base))
			split_ok = False
	else:
		log.error('failed to extract the ova file %s/%s' % (conf.get('FILESERVER', 'nfs_mount'), src_ova_file))
		split_ok = False
	return split_ok


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
		log.info('Finished with ERRORS!!!\n')
	else:
		log.info('ALL FINISHED!!!\n')

	log.info('~~~ ~~~ ~~~ ~~~')

	# cleanup settings that need to be refereshed each run
	conf.remove_option('STATE', 'migrate_error')

