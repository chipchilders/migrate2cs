## Copyright (c) 2014 Citrix Systems, Inc. All Rights Reserved.
## You may only reproduce, distribute, perform, display, or prepare derivative works of this file pursuant to a valid license from Citrix.

import json
from lib.cloudstack import CloudStack, cs
import os
import pprint
import time
import logging


class CommonServices:

	def __init__(self, confMgr):
		self.confMgr = confMgr
		if not self.confMgr.has_section('STATE'): #cindy: should have been set, right? needed?
			self.confMgr.add_section('STATE') # STATE config section to maintain state of the running process

	def cs_discover_accounts(self):
		self.confMgr.refresh()
		if self.confMgr.has_option('STATE', 'cs_objs'):
			obj = json.loads(self.confMgr.get('STATE', 'cs_objs'))
		else:
			obj = {}

		accounts = cs.request(dict({'command':'listAccounts', 'listAll':True}))
		if accounts and 'account' in accounts:
			if 'accounts' not in obj:
				obj['accounts'] = {}
			for account in accounts['account']:
				display = '%s/%s' % (account['domain'], account['name'])
				if display not in obj['accounts']:
					obj['accounts'][display] = {'display':display, 'id':account['id'], 'account':account['name'], 'domain':account['domainid']}
				#pprint.pprint(account)

			self.confMgr.updateOptions([('STATE', 'cs_objs', obj)], True)
			self.confMgr.updateRunningConfig() # update the file to include the changes we have made
		return obj


	def cs_discover_account_resources(self, account):
		self.confMgr.refresh()
		if self.confMgr.has_option('STATE', 'cs_objs'):
			obj = json.loads(self.confMgr.get('STATE', 'cs_objs'))
		else:
			obj = {}

		if 'accounts' not in obj:
			obj['accounts'] = {}
		if account['display'] not in obj['accounts']:
			obj['accounts'][account['display']] = account

		users = cs.request(dict({
			'command':'listUsers', 
			'account':account['account'], 
			'domainid':account['domain'], 
			'state':'enabled',
			'listAll':True}))
		if users and 'user' in users:
			user_session = None
			for user in users['user']:
				if 'apikey' in user and 'secretkey' in user:
					user_session = CloudStack(
						protocol=self.confMgr.get('CLOUDSTACK', 'protocol'), 
						host=self.confMgr.get('CLOUDSTACK', 'host'), 
						uri=self.confMgr.get('CLOUDSTACK', 'uri'), 
						api_key=user['apikey'], 
						secret_key=user['secretkey'], 
						logging=self.confMgr.getboolean('CLOUDSTACK', 'logging'), 
						async_poll_interval=self.confMgr.getint('CLOUDSTACK', 'async_poll_interval'))
					break
			if not user_session:
				# add keys to the first user and use them...
				keys = cs.request(dict({'command':'registerUserKeys', 'id':users['user'][0]['id']}))
				if keys and 'userkeys' in keys:
					user_session = CloudStack(
						protocol=self.confMgr.get('CLOUDSTACK', 'protocol'), 
						host=self.confMgr.get('CLOUDSTACK', 'host'), 
						uri=self.confMgr.get('CLOUDSTACK', 'uri'), 
						api_key=keys['userkeys']['apikey'], 
						secret_key=keys['userkeys']['secretkey'], 
						logging=self.confMgr.getboolean('CLOUDSTACK', 'logging'), 
						async_poll_interval=self.confMgr.getint('CLOUDSTACK', 'async_poll_interval'))

			if user_session:
				zones = user_session.request(dict({'command':'listZones', 'available':'true'}))
				if zones and 'zone' in zones:
					obj['accounts'][account['display']]['zones'] = {}
					for zone in zones['zone']:
						display = zone['name']
						obj['accounts'][account['display']]['zones'][zone['id']] = {'display':display, 'network':zone['networktype'].strip().lower()}
						#pprint.pprint(zone)
						#print("")

				networks = user_session.request(dict({'command':'listNetworks', 'listAll':True}))
				if networks and 'network' in networks:
					obj['accounts'][account['display']]['networks'] = {}
					for network in networks['network']:
						display = '%s - %s' % (network['name'], network['cidr'] if 'cidr' in network else 'shared')
						obj['accounts'][account['display']]['networks'][network['id']] = {'display':display, 'zone':network['zoneid']}
						#pprint.pprint(network)
						#print("")

				offerings = user_session.request(dict({'command':'listServiceOfferings', 'issystem':'false'}))
				if offerings and 'serviceoffering' in offerings:
					obj['accounts'][account['display']]['offerings'] = {}
					for offering in offerings['serviceoffering']:
						display = '%s - %sx%sMhz, %sM' % (offering['name'], offering['cpunumber'], offering['cpuspeed'], offering['memory'])
						obj['accounts'][account['display']]['offerings'][offering['id']] = {'display':display}
						#pprint.pprint(offering)
						#print("")

		### Update the running.conf file
		self.confMgr.updateOptions([('STATE', 'cs_objs', obj)], True)
		self.confMgr.updateRunningConfig()
		return obj


	def get_log_list(self):
		""" Outputs a link for each file in the logs directory. """
		output = '<h2>Recent Logs</h2><div style="font-family:monospace; padding:5px;">'
		file_list = os.listdir('./logs')
		file_list.sort(reverse=True)
		for file_name in file_list:
			if os.path.isfile('./logs/'+file_name) and '.md' not in file_name:
				output = '%s<a href="/log/%s">%s</a><br />' % (output, file_name, file_name)
		return output+'</div>'


def createMigrationLog(confMgr):
	timeStamp = str(int(time.time()))
	confMgr.updateOptions([('STATE', 'migration_timestamp', timeStamp)])
	# logFilename = './logs/hyperv_migration_%s.log' % timeStamp
	hypervisorType = confMgr.get('HYPERVISOR', 'hypervisorType')
	# logFilename = './logs/%s_migration_%s.log' % (hypervisorType, self.confMgr.get('STATE', 'migration_timestamp'))
	logFilename = './logs/%s_migration_%s.log' % (hypervisorType, timeStamp)
	confMgr.updateOptions([
		('HYPERVISOR', 'migration_log_file', logFilename),
		('STATE', 'migrate_error', 'False')])
	logMgr = LogManager(logFilename)
	return logMgr.getLogger()

class LogManager:# add migration logging
	def __init__(self, logFilename):
		self.log = logging.getLogger()
		log_handler = logging.FileHandler(logFilename)
		log_format = logging.Formatter('%(asctime)s %(levelname)s: %(message)s')
		log_handler.setFormatter(log_format)
		self.log.addHandler(log_handler) 
		self.log.setLevel(logging.INFO)
	def getLogger(self):
		return self.log


