import os
import logging
from urllib.parse import urlencode
from enum import Enum
from time import sleep

from salt.exceptions import CommandExecutionError, SaltInvocationError
import salt.utils.http
import salt.utils.json


#
# View Documentation
# salt-call --local sys.doc rapyutaio.*
#


log = logging.getLogger(__name__)



CATALOG_HOST = "https://gacatalog.apps.rapyuta.io"
PROVISION_API_PATH = CATALOG_HOST + "/v2/service_instances"

CORE_API_HOST = "https://gaapiserver.apps.rapyuta.io"
DEVICE_API_BASE_PATH = CORE_API_HOST + "/api/device-manager/v0/"
DEVICE_API_PATH = DEVICE_API_BASE_PATH + "devices/"
DEVICE_COMMAND_API_PATH = DEVICE_API_BASE_PATH + 'cmd/'
DEVICE_METRIC_API_PATH = DEVICE_API_BASE_PATH + 'metrics/'
DEVICE_TOPIC_API_PATH = DEVICE_API_BASE_PATH + 'topics/'
DEVICE_LABEL_API_PATH = DEVICE_API_BASE_PATH + 'labels/'



class phase(Enum):
	def __str__(self):
		return str(self.value)

	INPROGRESS = 'In progress'
	PROVISIONING = 'Provisioning'
	SUCCEEDED = 'Succeeded'
	FAILED_TO_START = 'Failed to start'
	PARTIALLY_DEPROVISIONED = 'Partially deprovisioned'
	STOPPED = 'Deployment stopped'

POSITIVE_PHASES = [
	phase.INPROGRESS,
	phase.PROVISIONING,
	phase.SUCCEEDED,
]

class status(Enum):
	def __str__(self):
		return str(self.value)

	RUNNING = 'Running'
	PENDING = 'Pending'
	ERROR = 'Error'
	UNKNOWN = 'Unknown'
	STOPPED = 'Stopped'


__virtual_name__ = "rapyutaio"
def __virtual__():
	return __virtual_name__



def _error(ret, err_msg):
    ret['result'] = False
    ret['comment'] = err_msg
    return ret



def _get_config(project_id, auth_token):
	"""
	If there is no project_id or auth token provided, this
	will attempt to fetch it from the Salt configuration
	"""
	if not project_id and __salt__["config.option"]("rapyutaio.project_id"):
		project_id = __salt__["config.option"]("rapyutaio.project_id")

	if not auth_token and __salt__["config.option"]("rapyutaio.auth_token"):
		auth_token = __salt__["config.option"]("rapyutaio.auth_token")

	return (project_id, auth_token)



# -----------------------------------------------------------------------------
#
# Packages
#
# -----------------------------------------------------------------------------
def get_packages(phase=[],
                 project_id=None,
                 auth_token=None):
	"""
	List of package summaries in the project

	project_id

		string

	Authorization

		string

	phase

		array[string]

	name

		string

	version

		string

	salt-call --log-level=debug --local rapyutaio.packages phase=["In progress","Succeeded"]
	"""
	params = {
		'phase': phase,
	}
	url = CATALOG_HOST + "/v2/catalog?%s" % urlencode(params, doseq=True)
	try:
		response_body = __utils__['rapyutaio.api_request'](url=url,
		                                                   method="GET",
		                                                   project_id=project_id,
		                                                   auth_token=auth_token)
	except CommandExecutionError as e:
		log.exception(e)
		return None

	# The packages are listed under the "services" key
	return response_body['services']



def get_package(name=None,
                version=None,
                guid=None,
                project_id=None,
                auth_token=None):
	"""
	Return a dict of information about a single package

	project_id

		string

	Authorization

		string

	guid

		string

	name

		string

	version

		string

	Returns:
		False: file not found
		Exception: something went wrong
		Dict: package
	"""
	if guid is None:
		if name is None or version is None:
			raise SaltInvocationError(
				"Require either 'guid', or 'name' and 'version'"
			)

		#
		# Fetch a single package via its name and version
		#
		packages = get_packages(project_id=project_id,
		                        auth_token=auth_token)

		# Need to accept version with and without the 'v' prefix
		if version[0] == 'v':
			version = version[1:]

		# Return the first package that matches the version
		for pkg_summary in packages:
			pkg_version = pkg_summary['metadata']['packageVersion']

			if pkg_version[0] == 'v':
				pkg_version = pkg_version[1:]

			if pkg_summary['name'] == name:
				if pkg_version == version:
					guid = pkg_summary['id']
					break

	if guid is None:
		return False

	#
	# Fetch a single package via its UID
	#
	url = CATALOG_HOST + "/serviceclass/status"
	params = {
		"package_uid": guid,
	}
	try:
		return __utils__['rapyutaio.api_request'](url=url,
	                                              method="GET",
	                                              params=params,
	                                              project_id=project_id,
	                                              auth_token=auth_token)
	except CommandExecutionError as e:
		log.exception(e)
		return None



def delete_package(name=None,
                   version=None,
                   guid=None,
                   project_id=None,
                   auth_token=None):
	"""
	Delete a package

	Return:
		True: file deleted
		False: file not there
		Exception: could not delete
	"""
	(project_id, auth_token) = _get_config(project_id, auth_token)

	if guid is None:
		if name is None or version is None:
			raise SaltInvocationError(
				"Require either 'guid', or 'name' and 'version'"
			)

		#
		# Fetch the package UID using its name and version
		#
		package = get_package(name=name,
		                      version=version,
		                      project_id=project_id,
		                      auth_token=auth_token)

		if package is False:
			return False

		guid = package['packageInfo']['guid']

	#
	# Send the delete request
	#
	url = CATALOG_HOST + "/serviceclass/delete"
	data = {
		"package_uid": guid,
	}
	try:
		__utils__['rapyutaio.api_request'](url=url,
		                                   method="DELETE",
		                                   params=data,
		                                   project_id=project_id,
		                                   auth_token=auth_token)
	except CommandExecutionError as e:
		log.exception(e)
		return False

	return True



def create_package(source=None,
                   manifest=None,
                   project_id=None,
                   auth_token=None):
	"""
	Upload a package manifest
	"""
	(project_id, auth_token) = _get_config(project_id, auth_token)

	if manifest is None:
		if source is None:
			raise SaltInvocationError(
				"create_or_update_package requires either source or manifest"
			)

		file_name = __salt__["cp.cache_file"](source)

		if file_name is not False:
			with __utils__['files.fopen'](file_name, "r") as _f:
				file_name_part, file_extension = os.path.splitext(file_name)

				if file_extension == '.json':
					manifest = __utils__['json.load'](_f)
				elif file_extension in ['.yaml', '.yml']:
					manifest = __utils__['yaml.load'](_f)
				else:
					raise SaltInvocationError(
						"Source file must be a JSON (.json) or YAML (.yaml, .yml) file"
					)
		else:
			raise CommandExecutionError(
				"File '{}' does not exist".format(file_name)
			)

	url = CATALOG_HOST + "/serviceclass/add"
	try:
		return __utils__['rapyutaio.api_request'](url=url,
		                                          method="POST",
		                                          data=manifest,
		                                          project_id=project_id,
		                                          auth_token=auth_token)
	except CommandExecutionError as e:
		log.exception(e)
		return False



# -----------------------------------------------------------------------------
#
# Networks
#
# -----------------------------------------------------------------------------
def get_networks(project_id=None,
                 auth_token=None):
	"""
	Get a list of all routed networks
	"""
	url = CATALOG_HOST + "/routednetwork"

	try:
		response_body = __utils__['rapyutaio.api_request'](url=url,
		                                                   method="GET",
		                                                   project_id=project_id,
		                                                   auth_token=auth_token)
	except CommandExecutionError as e:
		log.exception(e)
		return None

	networks = [
		network
		for network
		in response_body
		if network['internalDeploymentStatus']['phase'] in list(map(str, POSITIVE_PHASES))
	]

	return networks



def get_network(name=None,
                guid=None,
                project_id=None,
                auth_token=None):
	"""
	Get an active Routed Network
	"""
	if guid is None:
		if name is None:
			raise SaltInvocationError(
				"get_network needs either a valid guid or name"
			)

		networks = get_networks(project_id=project_id,
		                        auth_token=auth_token)

		for network in networks:
			if network['name'] == name:
				if network['internalDeploymentStatus']['phase'] in ['In Progress', 'Succeeded', 'Provisioning']:
					guid = network['guid']
					break

	if guid is None:
		# We have no guid and the name didn't
		# match an existing network so we return False
		return False

	url = CATALOG_HOST + "/routednetwork/%s" % guid
	try:
		return __utils__['rapyutaio.api_request'](url=url,
		                                          method="GET",
		                                          project_id=project_id,
		                                          auth_token=auth_token)
	except CommandExecutionError as e:
		log.exception(e)
		return None



def create_network(name,
                   ros_distro,
                   runtime,
                   parameters=None,
                   project_id=None,
                   auth_token=None):
	"""
	Create a new Routed Network
	"""
	(project_id, auth_token) = _get_config(project_id, auth_token)

	url = CATALOG_HOST + "/routednetwork"
	header_dict = {
		"accept": "application/json",
		"project": project_id,
		"Authorization": "Bearer " + auth_token,
	}
	data = {
		"name": name,
		"rosDistro": ros_distro,
		"runtime": runtime,
		"parameters": parameters or {},
	}

	response = __utils__['http.query'](url=url,
	                                   header_dict=header_dict,
	                                   method="POST",
	                                   data=__utils__['json.dumps'](data),
	                                   status=True)

	if 'error' in response:
		raise CommandExecutionError(
			response['error']
		)

	return __utils__['json.loads'](response['body'])



def delete_network(name=None,
                   guid=None,
                   project_id=None,
                   auth_token=None):
	"""
	"""
	(project_id, auth_token) = _get_config(project_id, auth_token)

	if name is not None:
		networks = get_networks(project_id=project_id,
		                        auth_token=auth_token)

		for network in networks:
			if network['name'] == name:
				guid = network['guid']
				break

	if guid is None:
		raise CommandExecutionError(
			"delete_network needs either a valid guid or name"
		)

	url = CATALOG_HOST + "/routednetwork/%s" % guid
	header_dict = {
		"accept": "application/json",
		"project": project_id,
		"Authorization": "Bearer " + auth_token,
	}
	response = __utils__['http.query'](url=url,
	                                   header_dict=header_dict,
	                                   method="DELETE",
	                                   status=True)
	log.debug(response)

	if response['status'] == 200:
		return True

	if 'error' in response:
		if response['status'] != 404:
			raise CommandExecutionError(response['error'])

	return False



# -----------------------------------------------------------------------------
#
# Deployments
#
# -----------------------------------------------------------------------------
def get_deployments(package_uid=None,
                    phase=list([str(pp) for pp in POSITIVE_PHASES]),
                    project_id=None,
                    auth_token=None,):
	"""
	salt-call --log-level=debug --local rapyutaio.list_deployments phase=["In progress","Succeeded"]
	"""
	(project_id, auth_token) = _get_config(project_id, auth_token)

	url = CATALOG_HOST + "/deployment/list"
	header_dict = {
		"accept": "application/json",
		"project": project_id,
		"Authorization": "Bearer " + auth_token,
	}
	params = {
		'package_uid': package_uid or '',
		'phase': phase,
	}

	url = CATALOG_HOST + "/deployment/list?%s" % urlencode(params, doseq=True)

	response = __utils__['http.query'](url=url,
	                                   header_dict=header_dict,
	                                   method="GET",
	                                   status=True)
	if 'error' in response:
		raise CommandExecutionError(
			response['error']
		)
	return __utils__['json.loads'](response['body'])


def get_deployment(name=None,
                   id=None,
                   project_id=None,
                   auth_token=None):
	"""
	"""
	(project_id, auth_token) = _get_config(project_id, auth_token)

	if name is not None:
		deployments = get_deployments(project_id=project_id,
		                              auth_token=auth_token)

		for deployment in deployments:
			if deployment['name'] == name:
				id = deployment['deploymentId']

	header_dict = {
		"accept": "application/json",
		"project": project_id,
		"Authorization": "Bearer " + auth_token,
	}
	url = CATALOG_HOST + "/serviceinstance/%s" % id

	response = __utils__['http.query'](url=url,
	                                   header_dict=header_dict,
	                                   method="GET",
	                                   status=True)

	if 'error' in response:
		if response['status'] == 404:
			return None

		raise CommandExecutionError(
			response['error']
		)

	return __utils__['json.loads'](response['body'])



def create_deployment(name,
                      package_uid=None,
                      package_name=None,
                      package_version=None,
                      networks=None,
                      parameters={},
                      dependencies=[],
                      project_id=None,
                      auth_token=None):
	"""
	"""
	(project_id, auth_token) = _get_config(project_id, auth_token)

	if package_uid is None:
		if package_name is None or package_version is None:
			raise SaltInvocationError(
				"create_deployment requires package_uid, or package_name and package_version"
			)

	#
	# Create provision configuration
	#
	package = get_package(name=package_name,
	                      version=package_version,
	                      guid=package_uid,
	                      project_id=project_id,
	                      auth_token=auth_token)

	if package:
		plan = package['packageInfo']['plans'][0]
	else:
		raise CommandExecutionError(
			"Could not find package '{0}'".format(package_name)
		)

	provision_configuration = {
		"accepts_incomplete": True,
		"api_version": '1.0.0',
		"context": {
			"dependentDeployments": [],
			"labels": [],
			"name": name,
		},
		"parameters": {
			"global": {},
		},
		"plan_id": plan['planId'],
		"service_id": package['packageInfo']['guid'],
		"space_guid": "spaceGuid",
		'instance_id': 'instanceId',
		'organization_guid': 'organizationGuid',
	}

	for component in plan['components']['components']:
		for internal_component in plan['internalComponents']:
			if internal_component['componentName'] == component['name']:
				component_id = internal_component['componentId']
				break

		component_parameters = {
			"component_id": component_id,
			# "bridge_params": {
			# 	"alias": component['name']
			# }
		}
		for pkg_parameter in component['parameters']:
			# component_parameters[pkg_parameter['name']] = pkg_parameter.get('default', None)
			component_parameters[pkg_parameter['name']] = parameters.get(component['name'], {}).get(pkg_parameter['name'], pkg_parameter.get('default', None))

		provision_configuration['parameters'][component_id] = component_parameters

	#
	# Add routed networks
	#
	if networks is not None:
		all_routed_networks = get_networks(project_id=project_id,
		                                   auth_token=auth_token)
		network_names = networks.split(",")
		network_guids = []
		for network in all_routed_networks:
			if network['name'] in network_names:
				network_guids.append({
					"guid": network['guid']
				})

		provision_configuration['context']['routedNetworks'] = network_guids

	#
	# Dependencies
	#
	for dep_name in dependencies:
		dep_dpl = __salt__['rapyutaio.get_deployment'](name=dep_name)

		if dep_dpl is not None:
			provision_configuration['context']['dependentDeployments'].append({
				"dependentDeploymentId": dep_dpl['deploymentId']
			})

	#
	# Provision
	#
	url = PROVISION_API_PATH + "/instanceId"
	header_dict = {
		"accept": "application/json",
		"project": project_id,
		"Authorization": "Bearer " + auth_token,
		"Content-Type": "application/json",
	}
	response = __utils__['http.query'](url=url,
	                                   header_dict=header_dict,
	                                   method="PUT",
	                                   data=__utils__['json.dumps'](provision_configuration),
	                                   status=True)
	if 'error' in response:
		raise CommandExecutionError(
			response['error']
		)
	response_body = __utils__['json.loads'](response['body'])

	#
	# Wait for the deployment to complete
	#
	deployment_id = response_body['operation']
	deployment_phase = str(phase.INPROGRESS)
	while deployment_phase in list(map(str, [phase.INPROGRESS, phase.PROVISIONING])):
		sleep(10)

		deployment = get_deployment(id=deployment_id)
		deployment_phase = deployment['phase']

	if deployment_phase == str(phase.SUCCEEDED):
		return deployment

	return False



def delete_deployment(name=None,
                      id=None,
                      package_uid=None,
                      plan_id=None,
                      project_id=None,
                      auth_token=None):
	"""
	Response:

		{"async":false,"component_status":null}
	"""
	(project_id, auth_token) = _get_config(project_id, auth_token)

	deployment = get_deployment(name=name,
	                            id=id,
	                            project_id=None,
	                            auth_token=None)

	if deployment is None:
		return "Deployment {} does not exist".format(name)

	header_dict = {
		"accept": "application/json",
		"project": project_id,
		"Authorization": "Bearer " + auth_token,
	}
	params = {
		"service_id": deployment['packageId'],
		"plan_id": deployment['planId'],
	}
	url = CATALOG_HOST + "/v2/service_instances/%s" % deployment['deploymentId']

	return __utils__['http.query'](url=url,
	                               header_dict=header_dict,
	                               method="DELETE",
	                               params=params)



def get_dependencies(deployment_id,
                     project_id=None,
                     auth_token=None):
	"""
	"""
	(project_id, auth_token) = _get_config(project_id, auth_token)

	header_dict = {
		"accept": "application/json",
		"project": project_id,
		"Authorization": "Bearer " + auth_token,
	}
	url = CATALOG_HOST + "/serviceinstance/%s/dependencies" % deployment_id

	return __utils__['http.query'](url=url,
	                               header_dict=header_dict,
	                               method="GET")



def get_manifest(guid,
                 project_id=None,
                 auth_token=None):
	"""
	Get a manifest for a package like you would through the web interface
	"""
	package = get_package(guid=guid,
	                      project_id=project_id,
	                      auth_token=auth_token)

	if not package:
		return False

	url = package['packageUrl']
	response_body = __utils__['rapyutaio.api_request'](url=url,
	                                                   method="GET",
	                                                   project_id=project_id,
	                                                   auth_token=auth_token)
	return response_body



# -----------------------------------------------------------------------------
#
# Devices
#
# -----------------------------------------------------------------------------
def get_devices(tgt="*",
                project_id=None,
                auth_token=None):
	"""
	"""
	url = DEVICE_API_PATH
	response_body = __utils__['rapyutaio.api_request'](url=url,
	                                                   method="GET",
	                                                   project_id=project_id,
	                                                   auth_token=auth_token)

	# filter the list of devices
	devices = [
		device
		for device
		in response_body['response']['data']
		if __utils__['rapyutaio.match'](tgt, device)
	]

	return devices



def get_device(name=None,
               device_id=None,
               project_id=None,
               auth_token=None):
	"""
	"""
	(project_id, auth_token) = _get_config(project_id, auth_token)

	if device_id is None:
		if name is None:
			raise SaltInvocationError(
				"get_device requires device_id or name"
			)

		all_devices = get_devices(tgt=name,
		                          project_id=project_id,
		                          auth_token=auth_token)

		device_id = all_devices[0]['uuid']

	url = DEVICE_API_PATH + device_id
	response_body = __utils__['rapyutaio.api_request'](url=url,
	                                                   method="GET",
	                                                   project_id=project_id,
	                                                   auth_token=auth_token)
	return response_body['response']['data']



# -----------------------------------------------------------------------------
#
# Commands
#
# -----------------------------------------------------------------------------
def cmd(tgt,
        cmd,
        shell=None,
        env={},
        bg=False,
        runas=None,
        cwd=None,
        project_id=None,
        auth_token=None):
	"""
	Execute a command on one or more devices

	CLI Example::

		salt '*' rapyutaio.cmd \\* ls cwd=/etc/
	"""
	(project_id, auth_token) = _get_config(project_id, auth_token)

	#
	# Get devices
	#
	all_devices = get_devices(project_id=project_id, auth_token=auth_token)

	# A dict of devices to send the command, also serves as a UUID to name lookup
	device_names = {
		device['uuid']: device['name']
		for device
		in all_devices
		if __utils__['rapyutaio.match'](tgt, device)
		and device['status'] == "ONLINE"
	}

	if device_names:
		url = DEVICE_COMMAND_API_PATH
		header_dict = {
			"accept": "application/json",
			"project": project_id,
			"Authorization": "Bearer " + auth_token,
			"Content-Type": "application/json",
		}
		log.debug(header_dict)

		# Copy only the set function args into the command dict
		command = {
			key: val
			for key, val
			in locals().items()
			if key
			in ['cmd',
			    'shell',
			    'env',
			    'bg',
			    'runas',
			    'cwd']
			and val
		}
		command.update({"device_ids": list(device_names.keys())})

		response = __utils__['http.query'](url=url,
		                                   header_dict=header_dict,
		                                   method="POST",
		                                   data=__utils__['json.dumps'](command),
		                                   status=True)
		if 'error' in response:
			raise CommandExecutionError(
				response['error']
			)
		response_body = __utils__['json.loads'](response['body'])

		# Response uses device UUID as key, change to device name
		return {
			device_names[uuid]: output
			for uuid, output
			in response_body['response']['data'].items()
		}

	return False


# -----------------------------------------------------------------------------
#
# Metrics
#
# -----------------------------------------------------------------------------
def get_metrics(name=None,
                device_id=None,
                project_id=None,
                auth_token=None):
	"""
	"""
	(project_id, auth_token) = _get_config(project_id, auth_token)

	if device_id is None:
		if name is None:
			raise SaltInvocationError(
				"get_device requires device_id or name"
			)

		device = get_device(name=name,
		                    device_id=device_id,
		                    project_id=project_id,
		                    auth_token=auth_token)

		device_id = device['uuid']

	url = DEVICE_METRIC_API_PATH + device_id
	header_dict = {
		"accept": "application/json",
		"project": project_id,
		"Authorization": "Bearer " + auth_token,
	}
	response = __utils__['http.query'](url=url,
	                                   header_dict=header_dict,
	                                   method="GET",
	                                   status=True)
	if 'error' in response:
		raise CommandExecutionError(
			response['error']
		)

	response_body = __utils__['json.loads'](response['body'])
	return response_body['response']['data']



def add_metrics(name=None,
                device_id=None,
                metric_name=None,
                qos=None,
                project_id=None,
                auth_token=None):
	"""
	"""
	(project_id, auth_token) = _get_config(project_id, auth_token)

	if device_id is None:
		if name is None:
			raise SaltInvocationError(
				"get_device requires device_id or name"
			)

		device = get_device(name=name,
		                    device_id=device_id,
		                    project_id=project_id,
		                    auth_token=auth_token)

		device_id = device['uuid']

	if not qos.isdigit():
		try:
			qos = {
				"low": 0,
				"medium": 1,
				"high": 2
			}[qos]
		except KeyError:
			raise SaltInvocationError(
				"qos should be one of low (0), medium (1), or high (2)"
			)

	url = DEVICE_METRIC_API_PATH + device_id
	header_dict = {
		"accept": "application/json",
		"project": project_id,
		"Authorization": "Bearer " + auth_token,
		"Content-Type": "application/json",
	}
	data = {
		"name": metric_name,
		"config": {
			"qos": qos,
		}
	}
	response = __utils__['http.query'](url=url,
	                                   header_dict=header_dict,
	                                   method="POST",
	                                   data=__utils__['json.dumps'](data),
	                                   status=True)
	if 'error' in response:
		raise CommandExecutionError(
			response['error']
		)

	return True



# -----------------------------------------------------------------------------
#
# Topics
#
# -----------------------------------------------------------------------------
def get_topics(name=None,
               device_id=None,
               project_id=None,
               auth_token=None):
	"""
	Returns a list of topics
	"""
	(project_id, auth_token) = _get_config(project_id, auth_token)

	if device_id is None:
		if name is None:
			raise SaltInvocationError(
				"get_device requires device_id or name"
			)

		device = get_device(name=name,
		                    device_id=device_id,
		                    project_id=project_id,
		                    auth_token=auth_token)

		device_id = device['uuid']

	url = DEVICE_METRIC_API_PATH + device_id
	header_dict = {
		"accept": "application/json",
		"project": project_id,
		"Authorization": "Bearer " + auth_token,
	}
	response = __utils__['http.query'](url=url,
	                                   header_dict=header_dict,
	                                   method="GET",
	                                   status=True)
	if 'error' in response:
		raise CommandExecutionError(
			response['error']
		)

	response_body = __utils__['json.loads'](response['body'])
	return response_body['response']['data']



# -----------------------------------------------------------------------------
#
# Labels
#
# -----------------------------------------------------------------------------
def _label_add(device_id, name, value, project_id, auth_token):
	url = DEVICE_LABEL_API_PATH + str(device_id)
	data = {
		name: value,
	}
	response_body = __utils__['rapyutaio.api_request'](url=url,
	                                                   method="POST",
	                                                   data=data,
	                                                   project_id=project_id,
	                                                   auth_token=auth_token)
	return response_body['response']['data']



def _label_update(label_id, name, value, project_id, auth_token):
	url = DEVICE_LABEL_API_PATH + str(label_id)
	data = {
		"key": name,
		"value": value,
	}
	response_body = __utils__['rapyutaio.api_request'](url=url,
	                                                   method="PUT",
	                                                   data=data,
	                                                   project_id=project_id,
	                                                   auth_token=auth_token)
	return response_body['response']['data']



def _label_delete(label_id, project_id, auth_token):
	url = DEVICE_LABEL_API_PATH + str(label_id)
	response_body = __utils__['rapyutaio.api_request'](url=url,
	                                                   method="DELETE",
	                                                   project_id=project_id,
	                                                   auth_token=auth_token)
	return response_body['response']['data']



def label(tgt,
          name,
          value,
          project_id=None,
          auth_token=None):
	"""
	Set a label on one or more devices
	"""
	devices = get_devices(tgt, project_id=project_id, auth_token=auth_token)

	changes = {
		"added": [],
		"deleted": [],
		"updated": [],
	}
	for device in devices:
		device_labels = {l['key']: l for l in device['labels']}
		log.debug(device_labels)

		try:
			label = device_labels[name]
		except KeyError:
			if value != "":
				# add label
				_label_add(device['uuid'], name, value, project_id, auth_token)
				changes['added'].append(device['name'])
		else:
			if value == "":
				# delete label
				_label_delete(label['id'], project_id, auth_token)
				changes['deleted'].append(device['name'])
			elif value != device_labels[name]['value']:
				# update label
				_label_update(label['id'], name, value, project_id, auth_token)
				changes['updated'].append(device['name'])

	return {
		"label": name,
		"value": value,
		"changes": changes,
	}



def test(project_id=None, auth_token=None):
	"""
	Just for testing
	"""
	return __utils__['rapyutaio.api_request'](url=DEVICE_API_PATH,
	                                          method="GET",
	                                          project_id=project_id,
	                                          auth_token=auth_token)

