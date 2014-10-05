## Copyright (c) 2014 Citrix Systems, Inc. All Rights Reserved.
## You may only reproduce, distribute, perform, display, or prepare derivative works of this file pursuant to a valid license from Citrix.

import json
import os
import bottle

def setupCommon(confMgrIn, commonServiceIn):
	global confMgr, commonService
	confMgr = confMgrIn
	commonService = commonServiceIn
	# hypervisor_ui_mod = "ui_server_%s" % currentHypervisor
	# specializedControllerName = "%s_controller" % currentHypervisor
	# specializedController = __import__(hypervisor_ui_mod, [specializedControllerName]) 

############################################################################################################
###  COMMON BOTTLE ROUTES  ###
############################################################################################################

# get resources associated with an account
@bottle.route('/discover/account', method='POST')
def discover_account():
	account = None
	if bottle.request.params.account:
		account = json.loads(bottle.request.params.account)
	if account:
		bottle.response.content_type = 'application/json'
		resources = commonService.cs_discover_account_resources(account)
		return json.dumps(resources)
	else:
		return bottle.abort(500, 'Account was not defined correctly.')


# save the 'vms' object from the client to the running.conf
@bottle.route('/vms/save', method='POST')
def save_vms():
	print("************************* %s *********************" % bottle.request.params.vms.__class__)
	if bottle.request.params.vms:
		confMgr.refresh()
		vms = json.loads(bottle.request.params.vms)
		confMgr.updateOptions([('STATE', 'vms', vms)], True)
		confMgr.updateRunningConfig() # update the file to include the changes we have made
		return 'ok'
	else:
		return bottle.abort(500, 'Unable to save the VMs on the server.')


# pull the vms from the running config and refresh the UI
@bottle.route('/vms/refresh')
def refresh_vms():
	confMgr.refresh()
	vms = json.loads(confMgr.get('STATE', 'vms'))
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


# migration page
@bottle.route('/')
@bottle.view('index')
def index():
	variables = {}
	print confMgr.__class__
	print(confMgr.get('STATE', 'migration_timestamp'))
	print("....4....%s" %confMgr.getboolean('WEBSERVER', 'debug'))
	print(".....4...%s" %confMgr.get('WEBSERVER', 'port'))
	confMgr.refresh()
	confMgr.showAllConfigs()
	if not confMgr.getboolean('STATE', 'active_migration'):
		# openconfMgr.get('CLOUDSTACK', 'log_file'), 'w').close() # refresh the cs_request.log on reloads
		# openconfMgr.get('HYPERVISOR', 'log_file'), 'w').close() # refresh the hyperv_api.log on reloads
		# initCommon(HYPERVISOR_TYPE,confMgr.conf)
		csObjs = commonService.cs_discover_accounts()
		if len(csObjs) == 0:
			bottle.abort(500, "Could not get the CloudPlatform accounts.")
		variables['cs_objs'] = json.dumps(csObjs)
		vms, order = {},[]
		variables['vm_order'] = json.dumps(order)
		variables['vms'] = json.dumps(vms)
		variables['active_migration'] =confMgr.get('STATE', 'active_migration').lower()
	else:
		variables['cs_objs'] = json.dumps(json.loads(confMgr.get('STATE', 'cs_objs')))
		variables['vms'] = vms = json.dumps(json.loads(confMgr.get('STATE', 'vms')))
		variables['vm_order'] = json.dumps(json.loads(confMgr.get('STATE', 'vm_order')))
		variables['active_migration'] =confMgr.get('STATE', 'active_migration').lower()
	variables['log_list'] = commonService.get_log_list()
	return dict(variables)

