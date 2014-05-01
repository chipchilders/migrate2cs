## Copyright (c) 2014 Citrix Systems, Inc. All Rights Reserved.
## You may only reproduce, distribute, perform, display, or prepare derivative works of this file pursuant to a valid license from Citrix.

from ConfigParser import ConfigParser
import bottle
import json
from lib.cloudstack import CloudStack, cs
import os
import pprint
import subprocess

conf = ConfigParser()
# read in config files if they exist
conf.read(['./settings.conf', './running.conf'])

if not conf.has_section('STATE'):
	conf.add_section('STATE') # STATE config section to maintain state of the running process

###  FUNCTIONS  ###

def cs_discover_accounts():
	conf.read(['./running.conf'])
	if conf.has_option('STATE', 'cs_objs'):
		obj = json.loads(conf.get('STATE', 'cs_objs'))
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
			#print("")
	else:
		bottle.abort(500, "Could not get the CloudPlatform accounts.")

	### Update the running.conf file
	conf.set('STATE', 'cs_objs', json.dumps(obj))
	with open('running.conf', 'wb') as f:
		conf.write(f) # update the file to include the changes we have made
	return obj


def cs_discover_account_resources(account):
	conf.read(['./running.conf'])
	if conf.has_option('STATE', 'cs_objs'):
		obj = json.loads(conf.get('STATE', 'cs_objs'))
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
					protocol=conf.get('CLOUDSTACK', 'protocol'), 
					host=conf.get('CLOUDSTACK', 'host'), 
					uri=conf.get('CLOUDSTACK', 'uri'), 
					api_key=user['apikey'], 
					secret_key=user['secretkey'], 
					logging=conf.getboolean('CLOUDSTACK', 'logging'), 
					async_poll_interval=conf.getint('CLOUDSTACK', 'async_poll_interval'))
				break
		if not user_session:
			# add keys to the first user and use them...
			keys = cs.request(dict({'command':'registerUserKeys', 'id':users['user'][0]['id']}))
			if keys and 'userkeys' in keys:
				user_session = CloudStack(
					protocol=conf.get('CLOUDSTACK', 'protocol'), 
					host=conf.get('CLOUDSTACK', 'host'), 
					uri=conf.get('CLOUDSTACK', 'uri'), 
					api_key=keys['userkeys']['apikey'], 
					secret_key=keys['userkeys']['secretkey'], 
					logging=conf.getboolean('CLOUDSTACK', 'logging'), 
					async_poll_interval=conf.getint('CLOUDSTACK', 'async_poll_interval'))

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
	conf.set('STATE', 'cs_objs', json.dumps(obj))
	with open('running.conf', 'wb') as f:
		conf.write(f) # update the file to include the changes we have made
	return obj


def get_log_list():
	""" Outputs a link for each file in the logs directory. """
	output = '<h2>Recent Logs</h2><div style="font-family:monospace; padding:5px;">'
	file_list = os.listdir('./logs')
	file_list.sort(reverse=True)
	for file_name in file_list:
		if os.path.isfile('./logs/'+file_name) and '.md' not in file_name:
			output = '%s<a href="/log/%s">%s</a><br />' % (output, file_name, file_name)
	return output+'</div>'


###  COMMON BOTTLE ROUTES  ###

# get resources associated with an account
@bottle.route('/discover/account', method='POST')
def discover_account():
	account = None
	if bottle.request.params.account:
		account = json.loads(bottle.request.params.account)
	if account:
		bottle.response.content_type = 'application/json'
		resources = cs_discover_account_resources(account)
		return json.dumps(resources)
	else:
		return bottle.abort(500, 'Account was not defined correctly.')


# save the 'vms' object from the client to the running.conf
@bottle.route('/vms/save', method='POST')
def save_vms():
	if bottle.request.params.vms:
		conf.read(['./running.conf'])
		conf.set('STATE', 'vms', bottle.request.params.vms)
		with open('running.conf', 'wb') as f:
			conf.write(f) # update the file to include the changes we have made
		return 'ok'
	else:
		return bottle.abort(500, 'Unable to save the VMs on the server.')


# pull the vms from the running config and refresh the UI
@bottle.route('/vms/refresh')
def refresh_vms():
	conf.read(['./running.conf'])
	vms = json.loads(conf.get('STATE', 'vms'))
	return json.dumps(vms)


# grab the logs to update in the UI
@bottle.route('/logs/refresh')
def refresh_logs():
	return get_log_list()


# serve log files
@bottle.route('/log/<filepath:path>')
def serve_log(filepath):
	""" Download the requested log file. """
	bottle.response.set_header("Content-Type", "application/octet-stream")
	bottle.response.set_header("Content-Disposition", "attachment; filename=\""+filepath+"\";" )
	bottle.response.set_header("Content-Transfer-Encoding", "binary")
	return bottle.static_file(filepath, root='./logs/', download=True)


# serve a favicon.ico so the pages do not return a 404 for the /favicon.ico path in the browser.
@bottle.route('/favicon.ico')
def favicon():
    return bottle.static_file('favicon.png', root='./views/images/')

# routing for static files on the webserver
@bottle.route('/static/<filepath:path>')
def server_static(filepath):
	return bottle.static_file(filepath, root='./')


