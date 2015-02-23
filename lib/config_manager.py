#!/usr/bin/env python

## Copyright (c) 2014 Citrix Systems, Inc. All Rights Reserved.
## You may only reproduce, distribute, perform, display, or prepare derivative works of this file pursuant to a valid license from Citrix.

from ConfigParser import ConfigParser
import logging
import json
import pprint

migrationLog = logging.getLogger('migrationLog')

class ConfigManager:

	def __init__(self, configFileName, persistentStore, defaultConfigs):
		configFile = ConfigParser()
		for defaultConfig in defaultConfigs:
			section = defaultConfig[0]
			key = defaultConfig[1]
			value = defaultConfig[2]
			#migrationLog.info("--------%s--------%s %s" % (section, key, value))
			value = defaultConfig[2]
			if not configFile.has_section(section):
				configFile.add_section(section)
			if value and not configFile.has_option(section, key):
				configFile.set(section, key, value)
		configFile.read([configFileName, persistentStore])
		self.__dict__['persistentStore'] = persistentStore
		self.__dict__['_conf'] = configFile
		self.updateRunningConfig()

	def getConfig(self):
		return self.__dict__['_conf']

	def getPersistentStore(self):
		return self.__dict__['persistentStore']

	def __getattr__(self, attr):
		return getattr(self.getConfig(), attr)
	def __setattr__(self, attr, value):
		return setattr(self.getConfig(), attr, value)        

	def clearCachedConfig(self):
		"""this will remove the log history of the requests over multiple runs"""
		open(self.getConfig().get('HYPERVISOR', 'log_file'), 'w').close() # cleans the powershell requests log before execution so it only includes this run.
		open(self.getConfig().get('CLOUDSTACK', 'log_file'), 'w').close() # cleans the cloudstack requests log before execution so it only includes this run.

	def updateRunningConfig(self):
		with open(self.getPersistentStore(), 'wb') as f:
			self.getConfig().write(f) # update the file to include the changes we have made

	def updateOptions(self, configOptions, isJson=False):
		# we won't save the changes to file for every update, instead we wil let the client decide when it should be done.
		# maybe we can provide an option to do auto save after each update.
		for configOption in configOptions:
			section = configOption[0]
			key = configOption[1]
			value = configOption[2]
			if isJson:
				#migrationLog.info("------updating json--%s--------%s %s" % (section, key, json.dumps(value, indent=4)))
				self.getConfig().set(section, key, json.dumps(value, indent=4))
			else:
				#migrationLog.info("------updating--%s--------%s %s" % (section, key, value))
				self.getConfig().set(section, key, value)				
	
	def addOptionsToSection(self, section, configOptions, isJson=False):
		if not self.getConfig().has_section(section):
			self.getConfig().add_section(section)
			for configOption in configOptions:
				key = configOption[0]
				value = configOption[1]
				#migrationLog.info("------adding--%s--------%s %s" % (section, key, value))
				if isJson:
					self.getConfig().set(section, key, json.dumps(value, indent=4))
				else:
					self.getConfig().set(section, key, value)
			self.updateRunningConfig()


	def refresh(self):
		self.getConfig().read([self.getPersistentStore()])

	def showAllConfigs(self):
		for section in self.getConfig().sections(): 
			migrationLog.info("\n+++++++++++++++++++++++%s++++++++++++++++++++++++++++++++++" % (section))
			for item in self.getConfig().items(section):
				migrationLog.info("%s\t%s" % (section, item))
