import os
import logging
from urllib.parse import urlencode
from enum import Enum
from time import sleep

import salt.utils.http
import salt.utils.json
from salt.exceptions import CommandExecutionError, SaltInvocationError



log = logging.getLogger(__name__)



CORE_API_HOST = "https://gaapiserver.apps.rapyuta.io"
CATALOG_HOST = "https://gacatalog.apps.rapyuta.io"
PROVISION_API_PATH = '/v2/service_instances'
DEVICE_API_BASE_PATH = "/api/device-manager/v0/"
DEVICE_API_PATH = DEVICE_API_BASE_PATH + "devices/"
DEVICE_COMMAND_API_PATH = DEVICE_API_BASE_PATH + 'cmd/'
DEVICE_METRIC_API_PATH = DEVICE_API_BASE_PATH + 'metrics/'
DEVICE_TOPIC_API_PATH = DEVICE_API_BASE_PATH + 'topics/'

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
def get_packages(name=None,
                 phase=[],
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

	salt-call --log-level=debug --local rapyutaio.get_packages phase=["In progress","Succeeded"]
	"""
	(project_id, auth_token) = _get_config(project_id, auth_token)

	header_dict = {
		"accept": "application/json",
		"project": project_id,
		"Authorization": "Bearer " + auth_token,
	}
	params = {
		'phase': phase,
	}
	url = "https://gacatalog.apps.rapyuta.io/v2/catalog?%s" % urlencode(params, doseq=True)

	response =  __utils__['http.query'](url=url,
	                                    header_dict=header_dict,
	                                    method="GET")

	if 'error' in response:
		if response['status'] != 404:
			raise CommandExecutionError(response['error'])
		else:
			return []

	# The response "body" will be string of JSON
	try:
		response_body = __utils__['json.loads'](response['body'])
	except JSONDecodeError as e:
		raise CommandExecutionError(e)

	# The packages are listed under the "services" key
	try:
		packages = response_body['services']
	except KeyError as e:
		log.debug(response_body)
		raise CommandExecutionError(e)

	if name is not None:
		packages = [
			pkg for pkg in packages if pkg['name'] == name
		]

	log.debug(packages)

	return packages



def get_package(package_uid=None,
                name=None,
                version=None,
                project_id=None,
                auth_token=None):
	"""
	Return a dict of information about a single package

	project_id

		string

	Authorization

		string

	package_uid

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
	(project_id, auth_token) = _get_config(project_id, auth_token)

	if package_uid is None:
		if name is not None and version is not None:
			#
			# Fetch a single package via its name and version
			#
			packages = get_packages(name=name,
			                        project_id=project_id,
			                        auth_token=auth_token)

			# Don't try to process an error response
			if 'error' in packages:
				return packages

			# Need to accept version with and without the 'v' prefix
			if version[0] != 'v':
				version = 'v' + version

			# Return the first package that matches the version
			for pkg_summary in packages:
				if pkg_summary['metadata']['packageVersion'] == version:
					package_uid = pkg_summary['id']
		else:
			raise SaltInvocationError(
				"Require either 'package_uid', or 'name' and 'version'"
			)

	if package_uid is not None:
		#
		# Fetch a single package via its UID
		#
		url = "https://gacatalog.apps.rapyuta.io/serviceclass/status"
		header_dict = {
			"accept": "application/json",
			"project": project_id,
			"Authorization": "Bearer " + auth_token,
		}
		data = {
			"package_uid": package_uid,
		}
		response =  __utils__['http.query'](url=url,
		                                    header_dict=header_dict,
		                                    method="GET",
		                                    params=data,
		                                    status=True)

		if 'error' in response:
			if response['status'] != 404:
				raise CommandExecutionError(response['error'])
			else:
				return False

		return __utils__['json.loads'](response['body'])

	return False



def delete_package(package_uid=None,
                   name=None,
                   version=None,
                   project_id=None,
                   auth_token=None,
                   ):
	"""
	Delete a package

	Return:
		True: file deleted
		False: file not there
		Exception: could not delete
	"""
	(project_id, auth_token) = _get_config(project_id, auth_token)

	if package_uid is None:
		if name is not None and version is not None:
			#
			# Fetch the package UID using its name and version
			#
			package = get_package(name=name,
			                      version=version,
			                      project_id=project_id,
			                      auth_token=auth_token)

			if 'error' in package:
				return package

			package_uid = package['packageInfo']['guid']
		else:
			raise SaltInvocationError(
				"Require either 'package_uid', or 'name' and 'version'"
			)

	#
	# Send the delete request
	#
	url = "https://gacatalog.apps.rapyuta.io/serviceclass/delete"
	header_dict = {
		"accept": "application/json",
		"project": project_id,
		"Authorization": "Bearer " + auth_token,
	}
	data = {
		"package_uid": package_uid,
	}
	response =  __utils__['http.query'](url=url,
	                                    header_dict=header_dict,
	                                    method="DELETE",
	                                    params=data,
	                                    status=True)

	if response['status'] == 200:
		return True

	if 'error' in response:
		if response['status'] != 404:
			raise CommandExecutionError(response['error'])

	return False



def create_package(source=None,
                   content=None,
                   project_id=None,
                   auth_token=None,
                   dry_run=False):
	"""
	Upload a package manifest
	"""
	(project_id, auth_token) = _get_config(project_id, auth_token)

	if content is None:
		if source is None:
			raise SaltInvocationError(
				"create_or_update_package requires either source or content"
			)

		file_name = __salt__["cp.cache_file"](source)

		if file_name is not False:
			with salt.utils.files.fopen(file_name, "r") as _f:
				file_name_part, file_extension = os.path.splitext(file_name)

				if file_extension == '.json':
					content = __utils__['json.load'](_f)
				elif file_extension in ['.yaml', '.yml']:
					content = __utils__['yaml.load'](_f)
				else:
					raise SaltInvocationError(
						"Source file must be a JSON (.json) or YAML (.yaml, .yml) file"
					)
		else:
			raise CommandExecutionError(
				"File '{}' does not exist".format(file_name)
			)

	url = "https://gacatalog.apps.rapyuta.io/serviceclass/add"
	header_dict = {
		"accept": "application/json",
		"project": project_id,
		"Authorization": "Bearer " + auth_token,
	}
	response = __utils__['http.query'](url=url,
	                                   header_dict=header_dict,
	                                   method="POST",
	                                   data=__utils__['json.dumps'](content),
	                                   status=True)

	if 'error' in response:
		raise CommandExecutionError(
			response['error']
		)

	return __utils__['json.loads'](response['body'])



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

	(project_id, auth_token) = _get_config(project_id, auth_token)

	url = "https://gacatalog.apps.rapyuta.io/routednetwork"
	header_dict = {
		"accept": "application/json",
		"project": project_id,
		"Authorization": "Bearer " + auth_token,
	}

	response =  __utils__['http.query'](url=url,
	                                    header_dict=header_dict,
	                                    method="GET",
	                                    status=True)

	if 'error' in response:
		raise CommandExecutionError(
			response['error']
		)

	networks = __utils__['json.loads'](response['body'])

	networks = [
		network
		for network
		in networks
		if network['internalDeploymentStatus']['phase'] in list(map(str, POSITIVE_PHASES))
	]

	return networks



def get_network(network_guid=None,
                name=None,
                project_id=None,
                auth_token=None):
	"""
	Get an active Routed Network
	"""
	(project_id, auth_token) = _get_config(project_id, auth_token)

	if network_guid is None:
		if name is None:
			raise SaltInvocationError(
				"get_network needs either a valid guid or name"
			)

		networks = get_networks(project_id=project_id, auth_token=auth_token)

		for network in networks:
			if network['name'] == name:
				if network['internalDeploymentStatus']['phase'] in ['In Progress', 'Succeeded', 'Provisioning']:
					network_guid = network['guid']
					break

	if network_guid is None:
		# We have no network_guid and the name didn't
		# match an existing network so we return False
		return False

	url = "https://gacatalog.apps.rapyuta.io/routednetwork/%s" % network_guid
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
		if response['status'] != 404:
			raise CommandExecutionError(response['error'])
		else:
			return False

	return __utils__['json.loads'](response['body'])



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

	url = "https://gacatalog.apps.rapyuta.io/routednetwork"
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



def delete_network(network_guid=None,
                   name=None,
                   project_id=None,
                   auth_token=None):
	"""
	"""
	(project_id, auth_token) = _get_config(project_id, auth_token)

	if name is not None:
		networks = get_networks(project_id=project_id, auth_token=auth_token)

		for network in networks:
			if network['name'] == name:
				network_guid = network['guid']
				break

	if network_guid is None:
		raise CommandExecutionError(
			"delete_network needs either a valid guid or name"
		)

	url = "https://gacatalog.apps.rapyuta.io/routednetwork/%s" % network_guid
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
                    phase=list(map(str, POSITIVE_PHASES)),
                    project_id=None,
                    auth_token=None,):
	"""
	salt-call --log-level=debug --local rapyutaio.list_deployments phase=["In progress","Succeeded"]
	"""
	(project_id, auth_token) = _get_config(project_id, auth_token)

	url = "https://gacatalog.apps.rapyuta.io/deployment/list"
	header_dict = {
		"accept": "application/json",
		"project": project_id,
		"Authorization": "Bearer " + auth_token,
	}
	params = {
		'package_uid': package_uid or '',
		'phase': phase,
	}

	url = "https://gacatalog.apps.rapyuta.io/deployment/list?%s" % urlencode(params, doseq=True)

	response =  __utils__['http.query'](url=url,
	                                    header_dict=header_dict,
	                                    method="GET",
	                                    status=True)

	if 'error' in response:
		raise CommandExecutionError(
			response['error']
		)

	return __utils__['json.loads'](response['body'])


def get_deployment(deploymentid=None,
                   name=None,
                   project_id=None,
                   auth_token=None):
	"""
	"""
	(project_id, auth_token) = _get_config(project_id, auth_token)

	if name is not None:
		deployments = get_deployments(project_id=project_id, auth_token=auth_token)

		for deployment in deployments:
			if deployment['name'] == name:
				deploymentid = deployment['deploymentId']

	header_dict = {
		"accept": "application/json",
		"project": project_id,
		"Authorization": "Bearer " + auth_token,
	}
	url = "https://gacatalog.apps.rapyuta.io/serviceinstance/%s" % deploymentid

	response = __utils__['http.query'](url=url,
	                                   header_dict=header_dict,
	                                   method="GET",
	                                   status=True)

	if 'error' in response:
		if response['status'] == 404:
			return False

		raise CommandExecutionError(
			response['error']
		)

	return __utils__['json.loads'](response['body'])



def create_deployment(name,
                      package_uid,
                      routed_networks=[],
                      project_id=None,
                      auth_token=None):
	"""
	"""
	(project_id, auth_token) = _get_config(project_id, auth_token)

	# {
	# 	"accepts_incomplete": true,
	# 	"api_version": "1.0.0",
	# 	"context": {
	# 		"dependentDeployments": [],
	# 		"labels": [],
	# 		"routedNetworks": [
	# 			{
	# 				"guid": "net-tuyuexxtupcrjmxjunjfrdrs"
	# 			}
	# 		],
	# 		"name": "ROS PUBLISHER"
	# 	},
	# 	"instance_id": "instanceId",
	# 	"organization_guid": "organizationGuid",
	# 	"parameters": {
	# 		"global": {},
	# 		"iqqafabrjdmwmmnbpqkautfz": {
	# 			"bridge_params": {
	# 				"alias": "TALKER"
	# 			},
	# 			"component_id": "iqqafabrjdmwmmnbpqkautfz"
	# 		}
	# 	},
	# 	"plan_id": "plan-uuqfdaiaezzxidcamnvpxaxx",
	# 	"service_id": "pkg-vnejycpfzzlssisfsyaizxtq",
	# 	"space_guid": "spaceGuid"
	# }

	#
	# Create provision configuration
	#
	package = get_package(package_uid=package_uid,
	                      project_id=project_id,
	                      auth_token=auth_token)
	plan = package['packageInfo']['plans'][0]
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
		"service_id": package_uid,
		"space_guid": "spaceGuid",
		'instance_id': 'instanceId',
		'organization_guid': 'organizationGuid',
	}

	for component in plan['components']['components']:
		for internal_component in plan['internalComponents']:
			if internal_component['componentName'] == component['name']:
				component_id = internal_component['componentId']

		parameters = {
			"component_id": component_id,
			"bridge_params": {
				"alias": component['name']
			}
		}
		for params in component['parameters']:
			parameters[params['name']] = params.get('default', None)

		provision_configuration['parameters'][component_id] = parameters

	#
	# Add routed networks
	#
	all_routed_networks = get_networks(project_id=project_id,
	                                   auth_token=auth_token)
	routed_network_names = routed_networks.split(",")
	routed_network_guids = []
	for network in all_routed_networks:
		if network['name'] in routed_network_names:
			routed_network_guids.append({
				"guid": network['guid']
			})

	provision_configuration['context']['routedNetworks'] = routed_network_guids

	#
	# Provision
	#
	url = CATALOG_HOST + PROVISION_API_PATH + "/instanceId"
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

		deployment = get_deployment(deployment_id)
		deployment_phase = deployment['phase']

	if deployment_phase == str(phase.SUCCEEDED):
		return deployment

	return False



def delete_deployment(deploymentid=None,
                      package_uid=None,
                      plan_id=None,
                      name=None,
                      project_id=None,
                      auth_token=None):
	"""
	Response:

		{"async":false,"component_status":null}
	"""
	(project_id, auth_token) = _get_config(project_id, auth_token)

	if name is not None:
		deployment = get_deployment(name=name,
		                            project_id=None,
		                            auth_token=None)
	else:
		deployment = get_deployment(deploymentid=deploymentid,
		                            project_id=None,
		                            auth_token=None)

	header_dict = {
		"accept": "application/json",
		"project": project_id,
		"Authorization": "Bearer " + auth_token,
	}
	params = {
		"service_id": package_uid,
		"plan_id": plan_id,
	}
	url = "https://gacatalog.apps.rapyuta.io/v2/service_instances/%s" % deploymentid

	return __utils__['http.query'](url=url,
	                               header_dict=header_dict,
	                               method="DELETE",
	                               params=params)



def get_dependencies(deploymentid,
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
	url = "https://gacatalog.apps.rapyuta.io/serviceinstance/%s/dependencies" % deploymentid

	return __utils__['http.query'](url=url,
	                               header_dict=header_dict,
	                               method="GET")



def get_manifest(package_uid,
                 project_id=None,
                 auth_token=None):
	"""
	Get a manifest for a package like you would through the web interface
	"""
	(project_id, auth_token) = _get_config(project_id, auth_token)

	package = get_package(package_uid=package_uid,
	                      project_id=project_id,
	                      auth_token=auth_token)

	if not package:
		return False

	url = package['packageUrl']
	header_dict = {
		"accept": "application/json"
	}
	response = __utils__['http.query'](url=url,
	                                   header_dict=header_dict,
	                                   method="GET")

	if 'error' in response:
		raise CommandExecutionError(
			response['error']
		)

	return __utils__['json.loads'](response['body'])



# -----------------------------------------------------------------------------
#
# Devices
#
# -----------------------------------------------------------------------------
def get_devices(tgt=None,
                project_id=None,
                auth_token=None):
	"""
	"""
	(project_id, auth_token) = _get_config(project_id, auth_token)

	url = CORE_API_HOST + DEVICE_API_PATH
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

	# parse the response
	response_body = __utils__['json.loads'](response['body'])

	# filter the list of devices
	if tgt is not None:
		devices = [
			device
			for device
			in response_body['response']['data']
			if __salt__['match.compound'](tgt, device['name'])
		]
	else:
		devices = response_body['response']['data']

	return devices



def get_device(device_id=None,
               name=None,
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

	url = CORE_API_HOST + DEVICE_API_PATH + device_id
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

	# parse the response
	response_body = __utils__['json.loads'](response['body'])

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
	"""
	(project_id, auth_token) = _get_config(project_id, auth_token)

	#
	# Get devices
	#
	all_devices = get_devices(project_id=project_id, auth_token=auth_token)

	devices = [
		device['uuid']
		for device
		in all_devices
		if __salt__['match.compound'](tgt, device['name'])
		and device['status'] == "ONLINE"
	]

	if devices:
		url = CORE_API_HOST + DEVICE_COMMAND_API_PATH
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
		command.update({"device_ids": devices})

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
		return response_body['response']['data']

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

		device = get_device(device_id=device_id,
		                    name=name,
		                    project_id=project_id,
		                    auth_token=auth_token)

		device_id = device['uuid']

	url = CORE_API_HOST + DEVICE_METRIC_API_PATH + device_id
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

		device = get_device(device_id=device_id,
		                    name=name,
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

	url = CORE_API_HOST + DEVICE_METRIC_API_PATH + device_id
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

		device = get_device(device_id=device_id,
		                    name=name,
		                    project_id=project_id,
		                    auth_token=auth_token)

		device_id = device['uuid']

	url = CORE_API_HOST + DEVICE_METRIC_API_PATH + device_id
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
