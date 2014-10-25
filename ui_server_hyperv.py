#!/usr/bin/env python

## Copyright (c) 2014 Citrix Systems, Inc. All Rights Reserved.
## You may only reproduce, distribute, perform, display, or prepare derivative works of this file pursuant to a valid license from Citrix.

## ----------------------
##  INSTALL DEPENDANCIES
## ----------------------
## $ pip install bottle
## $ pip install rocket or cherrypy
##
## Author: Will Stevens 

import hashlib
import json
import pprint
from lib.hyperv import HyperV # the class
from lib.hyperv import hyperv # the connection
import ntpath
import os
import subprocess
import sys

from xml.etree import ElementTree as ET
import re
from lib.config_manager import ConfigManager
from ui_common import *
from migrate_hyperv import HypverMigrator
from common_services import CommonServices

import logging
import logging.handlers
import time


def setup():
	HYPERVISOR_TYPE = 'hyperv'
	defaultHypervConfig =[
	('HYPERVISOR', 'hypervisorType', HYPERVISOR_TYPE),
	('HYPERVISOR', 'migration_input_file', './input/migrate_hyperv_input.json'), 
	('HYPERVISOR', 'pscp_exe', 'C:\pscp.exe'),
	('HYPERVISOR', 'log_file', './logs/hyperv_api.log'),
	('WEBSERVER', 'debug', 'True'),
	('WEBSERVER', 'port', '8080'),
	('STATE', 'active_migration', 'False'),
	('DEBUG', 'ui_test', 'False'),
	('DEBUG', 'skip_discovery', 'False')
	]

	configFile = './settings-' + HYPERVISOR_TYPE + '.conf'
	persistentStore = './running-'+HYPERVISOR_TYPE+'.conf'
	confMgr = ConfigManager(configFile, persistentStore, defaultHypervConfig)

	# these common stuff are mostly for UI currently...
	commonService = CommonServices(confMgr)
	setupCommon(confMgr, commonService)

	# make sure we have an nfs mount point
	if not confMgr.has_option('FILESERVER', 'files_path'):
		sys.exit("Config required in settings-hyperv.conf: [FILESERVER] -> files_path")

	global serverlog
	serverlog = logging.getLogger('serverLog')
	log_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
	if confMgr.getboolean('WEBSERVER', 'debug'):
	    serverlog.setLevel(logging.DEBUG)
	else:
	    serverlog.setLevel(logging.INFO)
	logging.basicConfig(format='%(asctime)s %(message)s')
	log_file_handler = logging.handlers.TimedRotatingFileHandler('server.log', when='midnight', interval=1, backupCount=30)
	log_file_handler.setFormatter(log_formatter)
	serverlog.addHandler(log_file_handler)
	
	return confMgr

# start the migration
@bottle.route('/migration/start', method='POST')
def start_migration():
	if bottle.request.params.migrate:
		confMgr.updateOptions([('STATE', 'migrate', bottle.request.params.migrate)])
		confMgr.updateRunningConfig()
		confMgr.refresh()
		if not confMgr.getboolean('DEBUG', 'ui_test'):
			serverlog.info("spawing the migration process...")
			subprocess.Popen(['python', 'migrate_hyperv.py'])
		return 'ok'
	else:
		return bottle.abort(500, 'Could not start the migration...')

# get the migration log
@bottle.route('/migration/log')
def get_migration_log():
	output = ''
	confMgr.refresh()
	try:
		with open(confMgr.get('HYPERVISOR', 'migration_log_file'), 'r') as f:
			output = f.read()
	except:
		output = 'Log does not exist yet...'
	return output

# pull the vms from the running config and refresh the UI
@bottle.route('/vms')
def fetchVms():
	if confMgr.getboolean('DEBUG', 'skip_discovery'):
		serverlog.info("fetching vms from running.conf")
		vms = json.loads(confMgr.get('STATE', 'vms'))
		order = json.loads(confMgr.get('STATE', 'vm_order'))
	else:
		serverlog.info("fetching vms from src host")
		vms, order = hyperv_migrator.discover_vms()
	return json.dumps({'vms': vms, 'vm_order': order})


confMgr = setup()
hyperv_migrator = HypverMigrator(confMgr)

# start the server
bottle.run(
	server='cherrypy',
	host='0.0.0.0',
	port=confMgr.getint('WEBSERVER', 'port'),
	reloader=False,
	debug=confMgr.getboolean('WEBSERVER', 'debug'))
