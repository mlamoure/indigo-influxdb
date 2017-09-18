#! /usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2017, Dave Brown, Mike Lamoureux
#
# config reference
# http://wiki.indigodomo.com/doku.php?id=indigo_7_documentation:plugin_guide#configuration_dialogs
# device fields
# http://wiki.indigodomo.com/doku.php?id=indigo_7_documentation:device_class#device_base_class
# object reference
# http://wiki.indigodomo.com/doku.php?id=indigo_7_documentation:object_model_reference
# Subscribe to changes mentioned:
# http://forums.indigodomo.com/viewtopic.php?f=108&t=14647
#
# CREATE USER indigo WITH PASSWORD 'indigo'
# GRANT ALL PRIVILEGES TO indigo
#
import indigo
import time as time_
import datetime
import json
from indigo_adaptor import IndigoAdaptor
from influxdb import InfluxDBClient
from influxdb.exceptions import InfluxDBClientError
from ghpu import GitHubPluginUpdater

DEFAULT_POLLING_INTERVAL = 60  # number of seconds between each poll

class Plugin(indigo.PluginBase):
	def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
		super(Plugin, self).__init__(pluginId, pluginDisplayName, pluginVersion, pluginPrefs)
		indigo.devices.subscribeToChanges()
		indigo.variables.subscribeToChanges()
		self.connection = None
		self.adaptor = IndigoAdaptor()
		self.folders = {}
		self.miniumumUpdateFrequency = int(pluginPrefs.get("txtMinimumUpdateFrequency", DEFAULT_POLLING_INTERVAL))
		self.pollingInterval = 60

		self.mode = pluginPrefs.get("ddlMode")
		self.debug = pluginPrefs.get("debug", False)

		try:
			if self.mode == "include":
				self.globalIncludeStates = pluginPrefs.get("txtGlobalInclude").replace(" ", "").split(",")
			else:
				self.globalExcludeStates = pluginPrefs.get("txtGlobalExclude").replace(" ", "").split(",")
		except:
			indigo.server.log(u'Problem parsing the inclusion / exclusion properties, check plugin config')

		self.updater = GitHubPluginUpdater(self)
		self.updater.checkForUpdate(str(self.pluginVersion))
		self.lastUpdateCheck = datetime.datetime.now()
		self.varUpdateCheck = []
		self.devUpdateCheck = []

	def checkForUpdates(self):
		self.updater.checkForUpdate()

	def updatePlugin(self):
		self.updater.update()

	def connect(self):
		indigo.server.log(u'Starting influx connection')

		self.connection = InfluxDBClient(
			host=self.host,
			port=int(self.port),
			username=self.user,
			password=self.password,
			database=self.database)

		if self.pluginPrefs.get('reset', False):
			try:
				indigo.server.log(u'dropping old')
				self.connection.drop_database(self.database)
			except:
				pass

		try:
			indigo.server.log(u'Connecting...')
			self.connection.create_database(self.database)
			self.connection.switch_database(self.database)
			self.connection.create_retention_policy('two_year_policy', '730d', '1')
			indigo.server.log(u'Influx connection succeeded')
			self.connected = True
		except:
			self.connected = False

	# send this a dict of what to write
	def send(self, tags, what, measurement='device_changes'):
		if not self.connected:
			return

		json_body=[
			{
				'measurement': measurement,
				'tags' : tags,
				'fields':  what
			}
		]

#		if self.pluginPrefs.get(u'debug', False):
#			indigo.server.log(json.dumps(json_body).encode('utf-8'))

		# don't like my types? ok, fine, what DO you want?
		retrylimit = 30
		unsent = True
		while unsent and retrylimit > 0:
			retrylimit -= 1
			try:
				self.connection.write_points(json_body)
				unsent = False
			except InfluxDBClientError as e:
				#print(str(e))
				field = json.loads(e.content)['error'].split('"')[1]
				#measurement = json.loads(e.content)['error'].split('"')[3]
				retry = json.loads(e.content)['error'].split('"')[4].split()[7]
				if retry == 'integer':
					retry = 'int'
				if retry == 'string':
					retry = 'str'
				# float is already float
				# now we know to try to force this field to this type forever more
				self.adaptor.typecache[field] = retry
				try:
					newcode = '%s("%s")' % (retry, str(json_body[0]['fields'][field]))
					#indigo.server.log(newcode)
					json_body[0]['fields'][field] = eval(newcode)
				except ValueError:
					pass
					#indigo.server.log('One of the columns just will not convert to its previous type. This means the database columns are just plain wrong.')
			except ValueError:
				if self.pluginPrefs.get(u'debug', False):
					indigo.server.log(u'Unable to force a field to the type in Influx - a partial record was still written')
			except Exception as e:
				indigo.server.log("Error while trying to write:")
				indigo.server.log(unicode(e))
		if retrylimit == 0 and unsent:
			if self.pluginPrefs.get(u'debug', False):
				indigo.server.log(u'Unable to force all fields to the types in Influx - a partial record was still written')

	def runConcurrentThread(self):
		self.logger.debug("Starting concurrent tread")

		self.sleep(int(self.pollingInterval))

		try:
			# Polling - As far as what is known, there is no subscription method using web standards available from August.
			while True:
				try:
					if self.connected:
						self.updateAll()

				except:
					pass

				self.sleep(int(self.pollingInterval))

		except self.StopThread:
			self.logger.debug("Received StopThread")

	def updateAll(self):
		if self.debug:
			self.logger.debug("running Update All")

		for dev in indigo.devices:
			needsUpdating = False
			found = False

			for devSearch in self.devUpdateCheck:
				if devSearch[0] == dev.name:
					found = True

					if devSearch[1] + datetime.timedelta(seconds=self.miniumumUpdateFrequency) < datetime.datetime.now():
						if self.debug:
							indigo.server.log("minimum update frequency for device expired: " + dev.name)

						needsUpdating = True
						devSearch[1] = datetime.datetime.now()

					break

			if not found:
				self.devUpdateCheck.append([dev.name, dev.lastChanged])

			if needsUpdating:
				self.influxDevice(dev, dev, True)

		for var in indigo.variables:
			needsUpdating = False
			found = False

			for varSearch in self.varUpdateCheck:
				if varSearch[0] == var.name:
					found = True

					if varSearch[1] + datetime.timedelta(seconds=self.miniumumUpdateFrequency) < datetime.datetime.now():
						if self.debug:
							indigo.server.log("minimum update frequency for variable expired: " + var.name)

						needsUpdating = True
						varSearch[1] = datetime.datetime.now()

					break

			if not found:
				self.varUpdateCheck.append([var.name, datetime.datetime.now()])

			if needsUpdating:
				self.influxVariable(var)




	def startup(self):
		try:
			self.host = self.pluginPrefs.get('host', 'localhost')
			self.port = self.pluginPrefs.get('port', '8086')
			self.user = self.pluginPrefs.get('user', 'indigo')
			self.password = self.pluginPrefs.get('password', 'indigo')
			self.database = self.pluginPrefs.get('database', 'indigo')

			self.connect()
		except:
			indigo.server.log(u'Failed to connect in startup')
			pass

		self.updateAll()

	# called after runConcurrentThread() exits
	def shutdown(self):
		pass

	def deviceUpdated(self, origDev, newDev):
		# call base implementation
		indigo.PluginBase.deviceUpdated(self, origDev, newDev)

		if self.debug:
			indigo.server.log("An update for device " + origDev.name + " is being processed...")

		device_was_updated = self.influxDevice(origDev, newDev, False)

		if not device_was_updated:
			if self.debug:
				indigo.server.log("An update for device " + origDev.name + " resulted in no properties updated...")

			return

		found = False
		for devSearch in self.devUpdateCheck:
			if devSearch[0] == origDev.name:
				found = True

				devSearch[1] = datetime.datetime.now()
				break

		if not found:
			self.devUpdateCheck.append([origDev.name, datetime.datetime.now()])

	def closedPrefsConfigUi(self, valuesDict, userCancelled):
		if not userCancelled:
			self.miniumumUpdateFrequency = int(valuesDict["txtMinimumUpdateFrequency"])
			self.mode = valuesDict["ddlMode"]

			try:
				if self.mode == "include":
					self.globalIncludeStates = valuesDict["txtGlobalInclude"].replace(" ", "").split(",")
				else:
					self.globalExcludeStates = valuesDict["txtGlobalExclude"].replace(" ", "").split(",")
			except:
				indigo.server.log(u'Problem parsing the inclusion / exclusion properties, check plugin config')

			self.host = valuesDict['host']
			self.port = valuesDict['port']
			self.user = valuesDict['user']
			self.password = valuesDict['password']
			self.database = valuesDict['database']
			self.debug = valuesDict["debug"]


			self.connect()



	def influxDevice(self, origDev, newDev, sendPulse):
		includeExcludeStates = []

		if self.mode == "include":
			includeExcludeStates = self.globalIncludeStates[:]
		else:
			includeExcludeStates = self.globalExcludeStates[:]

		if "com.indigodomo.indigoserver" in origDev.globalProps:
			if "influxIncStates" in origDev.globalProps["com.indigodomo.indigoserver"] and self.mode == "include":
				if self.debug:
					indigo.server.log(u'Including custom device properties (' + origDev.globalProps["com.indigodomo.indigoserver"]["influxIncStates"] + ") to the include states for device " + newDev.name)

				if "," in origDev.globalProps["com.indigodomo.indigoserver"]["influxIncStates"]:
					includeExcludeStates.append(origDev.globalProps["com.indigodomo.indigoserver"]["influxIncStates"].replace(" ", "").split(","))
				else:
					includeExcludeStates.append(origDev.globalProps["com.indigodomo.indigoserver"]["influxIncStates"])

				if self.debug:
					indigo.server.log("Include list: ")
					for item in includeExcludeStates:
						indigo.server.log(item)

			elif "influxExclStates" in origDev.globalProps["com.indigodomo.indigoserver"] and self.mode == "exclude":
				includeExcludeStates.append(origDev.globalProps["com.indigodomo.indigoserver"]["influxExclStates"].replace(" ", "").split(","))

		# custom add to influx work
		# tag by folder if present
		tagnames = u'name folderId'.split()

		if self.mode == "include" and "all" in includeExcludeStates:
			if self.debug:
				indigo.server.log("Sending all attributes to be sent for device " + newDev.name)

			newjson = self.adaptor.diff_to_json(newDev, "exclude", [], sendPulse)
		elif self.mode == "exclude" and "all" in includeExcludeStates:
			if self.debug:
				indigo.server.log("Sending NO attributes to be sent to InfluxDB for device " + newDev.name)

			return False
		else:
			newjson = self.adaptor.diff_to_json(newDev, self.mode, includeExcludeStates, sendPulse)

		if newjson == None:
			return False

		newtags = {}
		for tag in tagnames:
			newtags[tag] = unicode(getattr(newDev, tag))

		# add a folder name tag
		if hasattr(newDev, u'folderId') and newDev.folderId != 0:
			newtags[u'folder'] = indigo.devices.folders[newDev.folderId].name

		measurement = newjson[u'measurement']
		del newjson[u'measurement']
		self.send(tags=newtags, what=newjson, measurement=measurement)

		return True

	def variableUpdated(self, origVar, newVar):
		indigo.PluginBase.variableUpdated(self, origVar, newVar)

		found = False
		for varSearch in self.varUpdateCheck:
			if varSearch[0] == origVar.name:
				found = True

				varSearch[1] = datetime.datetime.now()
				break

		if not found:
			self.varUpdateCheck.append([origVar.name, datetime.datetime.now()])

		self.influxVariable(newVar)

	def influxVariable(self, var):
		newtags = {u'varname': var.name}
		newjson = {u'name': var.name, u'value': var.value }
		numval = self.adaptor.smart_value(var.value, True)
		if numval != None:
			newjson[u'value.num'] = numval

		self.send(tags=newtags, what=newjson, measurement=u'variable_changes')
