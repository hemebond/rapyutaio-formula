import os
import logging
from urllib.parse import urlencode
from enum import Enum
from copy import deepcopy

import salt.utils.http
import salt.utils.json
from salt.exceptions import CommandExecutionError




log = logging.getLogger(__name__)



class phase(Enum):
	def __str__(self):
		return str(self.value)

	INPROGRESS = 'In progress'
	PROVISIONING = 'Provisioning'
	SUCCEEDED = 'Succeeded'
	FAILED_TO_START = 'Failed to start'
	PARTIALLY_DEPROVISIONED = 'Partially deprovisioned'
	STOPPED = 'Deployment stopped'

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


def list_packages(project_id=None,
                  auth_token=None,
                  phase=[]):
	"""
	List all the packages in the project

	project_id

		string

	Authorization

		string

	phase

		array[string]

	salt-call --log-level=debug --local rapyutaio.list_packages phase=["In progress","Succeeded"]
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

	result =  salt.utils.http.query(url=url,
	                                header_dict=header_dict,
	                                method="GET")

	# The result "body" will be string of JSON
	result_body = salt.utils.json.loads(result['body'])

	# The packages are listed under the "services" key
	return result_body['services']



def get_packages(name=None,
                 version=None,
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
	params = {
		'phase': phase,
	}
	url = "https://gacatalog.apps.rapyuta.io/v2/catalog?%s" % urlencode(params, doseq=True)

	result =  salt.utils.http.query(url=url,
	                                header_dict=header_dict,
	                                method="GET")

	# The result "body" will be string of JSON
	result_body = salt.utils.json.loads(result['body'])

	# The packages are listed under the "services" key
	package_list = result_body['services']

	if name is not None:
		package_list = [
			pkg for pkg in package_list if pkg['name'] == name
		]

	if version is not None:
		if version[0] != 'v':
			version = 'v' + version

		package_list = [
			pkg for pkg in package_list if pkg['metadata']['packageVersion'] == version
		]

	log.debug(package_list)

	return package_list



def get_package(package_uid,
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
	"""

	(project_id, auth_token) = _get_config(project_id, auth_token)

	url = "https://gacatalog.apps.rapyuta.io/serviceclass/status"
	header_dict = {
		"accept": "application/json",
		"project": project_id,
		"Authorization": "Bearer " + auth_token,
	}
	data = {
		"package_uid": package_uid,
	}
	result =  salt.utils.http.query(url=url,
	                                header_dict=header_dict,
	                                method="GET",
	                                params=data,
	                                status=True)

	if 'error' in result:
		return {"result": False, "message": result['error']}

	try:
		result_body = salt.utils.json.loads(result['body'])
		return result_body
	except JSONDecodeError as e:
		return {"result": False, "message": e}



def delete_package(package_uid,
                   project_id=None,
                   auth_token=None):
	(project_id, auth_token) = _get_config(project_id, auth_token)

	url = "https://gacatalog.apps.rapyuta.io/serviceclass/delete"
	header_dict = {
		"accept": "application/json",
		"project": project_id,
		"Authorization": "Bearer " + auth_token,
	}
	data = {
		"package_uid": package_uid,
	}
	response =  salt.utils.http.query(url=url,
	                                header_dict=header_dict,
	                                method="DELETE",
	                                params=data,
	                                status=True)

	log.debug(response)

	if 'error' in response:
		return {"result": False, "message": response['error']}

	return response

	try:
		response['body'] = salt.utils.json.loads(response['body'])
		return response
	except JSONDecodeError as e:
		return {"result": False, "message": e}



def create_or_update_package(name,
                             source=None,
                             content=None,
                             project_id=None,
                             auth_token=None,
                             dry_run=False):
	"""
	Upload a package manifest
	"""
	(project_id, auth_token) = _get_config(project_id, auth_token)

	url = "https://gacatalog.apps.rapyuta.io/serviceclass/add"
	header_dict = {
		"accept": "application/json",
		"project": project_id,
		"Authorization": "Bearer " + auth_token,
	}

	if content is None:
		if source is None:
			return {
				"result": False,
				"message": "create_or_update_package requires either source or content"
			}
		else:
			file_name = __salt__["cp.cache_file"](source)

			if os.path.exists(file_name):
				with salt.utils.files.fopen(file_name, "r") as _f:
					content = salt.utils.json.load(_f)
			else:
				log.error('File "%s" does not exist', file_name)
				return {"result": False, "message": 'File "{}" does not exist'.format(file_name)}

	content['name'] = name

	response = salt.utils.http.query(url=url,
	                                 header_dict=header_dict,
	                                 method="POST",
	                                 data=salt.utils.json.dumps(content),
	                                 status=True)
	log.debug(response)

	if 'error' in response:
		return {
			"status": response['status'],
			"result": False,
			"message": response['error']
		}

	try:
		response['body'] = salt.utils.json.loads(response['body'])
		response['result'] = True
		return response
	except JSONDecodeError as e:
		return {
			"status": response['status'],
			"result": False,
			"message": e
		}



def list_networks(project_id=None,
                  auth_token=None):
	"""
	List all routed networks
	"""

	(project_id, auth_token) = _get_config(project_id, auth_token)

	url = "https://gacatalog.apps.rapyuta.io/routednetwork"
	header_dict = {
		"accept": "application/json",
		"project": project_id,
		"Authorization": "Bearer " + auth_token,
	}

	return salt.utils.http.query(url=url,
	                             header_dict=header_dict,
	                             method="GET")



def get_network(network_guid,
                project_id=None,
                auth_token=None):
	"""
	Get a Routed Network
	"""
	(project_id, auth_token) = _get_config(project_id, auth_token)

	url = "https://gacatalog.apps.rapyuta.io/routednetwork/%s" % network_guid
	header_dict = {
		"accept": "application/json",
		"project": project_id,
		"Authorization": "Bearer " + auth_token,
	}

	return salt.utils.http.query(url=url,
	                             header_dict=header_dict,
	                             method="GET")





def add_network(project_id=None,
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


	ret = salt.utils.http.query(url=url,
	                            header_dict=header_dict,
	                            method="POST",
	                            data=salt.utils.json.dumps(contents))

	if ret['status'] == 409:
		# Conflict: netowkr already exists with this name
		pass

	return ret



def delete_network(network_guid,
                   project_id=None,
                   auth_token=None):
	"""
	"""
	(project_id, auth_token) = _get_config(project_id, auth_token)

	url = "https://gacatalog.apps.rapyuta.io/routednetwork/%s" % network_guid
	header_dict = {
		"accept": "application/json",
		"project": project_id,
		"Authorization": "Bearer " + auth_token,
	}

	return salt.utils.http.query(url=url,
	                             header_dict=header_dict,
	                             method="DELETE")



def list_deployments(project_id=None,
                     auth_token=None,
                     package_uid='',
                     phase=[]):
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
		'package_uid': package_uid,
		'phase': phase,
	}
	url = "https://gacatalog.apps.rapyuta.io/deployment/list?%s" % urlencode(params, doseq=True)

	return salt.utils.http.query(url=url,
	                             header_dict=header_dict,
	                             method="GET")


def get_deployment(deploymentid,
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
	url = "https://gacatalog.apps.rapyuta.io/serviceinstance/%s" % deploymentid

	return salt.utils.http.query(url=url,
	                             header_dict=header_dict,
	                             method="GET")



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

	return salt.utils.http.query(url=url,
	                             header_dict=header_dict,
	                             method="GET")


def deprovision(deploymentid,
                package_uid,
                plan_id,
                project_id=None,
                auth_token=None):
	"""
	Response:

		{"async":false,"component_status":null}
	"""
	(project_id, auth_token) = _get_config(project_id, auth_token)

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

	return salt.utils.http.query(url=url,
	                             header_dict=header_dict,
	                             method="DELETE",
	                             params=params)



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

	header_dict = {
		"accept": "application/json"
	}
	url = package['packageUrl']

	response = __utils__['http.query'](url=url,
	                                   header_dict=header_dict,
	                                   method="GET")

	try:
		manifest = salt.utils.json.loads(response['body'])
	except KeyError as e:
		log.debug(response)
		log.exception(e)
		raise e

	return manifest
