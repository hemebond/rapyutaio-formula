# -*- coding: utf-8 -*-
"""
This is a simple proxy-minion designed to connect to and communicate with
the Rapyuta.IO web service
"""
from __future__ import absolute_import

# Import python libs
import logging
import salt.utils.http
from salt.exceptions import CommandExecutionError, SaltInvocationError


# This must be present or the Salt loader won't load this module
__proxyenabled__ = ["rapyutaio"]



CATALOG_HOST = "https://gacatalog.apps.rapyuta.io"
PROVISION_API_PATH = CATALOG_HOST + "/v2/service_instances"

CORE_API_HOST = "https://gaapiserver.apps.rapyuta.io"
DEVICE_API_BASE_PATH = CORE_API_HOST + "/api/device-manager/v0/"
DEVICE_API_PATH = DEVICE_API_BASE_PATH + "devices/"
DEVICE_COMMAND_API_PATH = DEVICE_API_BASE_PATH + 'cmd/'
DEVICE_METRIC_API_PATH = DEVICE_API_BASE_PATH + 'metrics/'
DEVICE_TOPIC_API_PATH = DEVICE_API_BASE_PATH + 'topics/'


SYSTEM_CONFIG_PATHS = ("/lib/systemd/system", "/usr/lib/systemd/system")



# Variables are scoped to this module so we can have persistent data
# across calls to fns in here.
GRAINS_CACHE = {}
DETAILS = {}


# Want logging!
log = logging.getLogger(__file__)


# This does nothing, it's here just as an example and to provide a log
# entry when the module is loaded.
def __virtual__():
	"""
	Only return if all the modules are available
	"""
	log.debug("rest_sample proxy __virtual__() called...")
	return True


def _complicated_function_that_determines_if_alive():
    log.debug("=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-")
    log.debug("proxys alive() fn called")
    log.debug("=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-")
    return ping()


# Every proxy module needs an 'init', though you can
# just put DETAILS['initialized'] = True here if nothing
# else needs to be done.


def init(opts):
	log.debug("rapyutaio proxy init() called...")
	DETAILS["initialized"] = True

	# Save the REST URL
	DETAILS["url"] = opts["proxy"]["url"]

	# Make sure the REST URL ends with a '/'
	if not DETAILS["url"].endswith("/"):
		DETAILS["url"] += "/"


def alive(opts):
	"""
	This function returns a flag with the connection state.
	It is very useful when the proxy minion establishes the communication
	via a channel that requires a more elaborated keep-alive mechanism, e.g.
	NETCONF over SSH.
	"""
	log.debug("rapyutaio proxy alive() called...")
	return _complicated_function_that_determines_if_alive()


def initialized():
	"""
	Since grains are loaded in many different places and some of those
	places occur before the proxy can be initialized, return whether
	our init() function has been called
	"""
	return DETAILS.get("initialized", False)


def grains():
	"""
	Get the grains from the proxied device
	"""
	log.debug("rapyutaio proxy grains() called...")
	# if not DETAILS.get("grains_cache", {}):
	# 	r = salt.utils.http.query(
	# 		DETAILS["url"] + "info", decode_type="json", decode=True
	# 	)
	# 	DETAILS["grains_cache"] = r["dict"]
	# return DETAILS["grains_cache"]
	return {}


def grains_refresh():
	"""
	Refresh the grains from the proxied device
	"""
	log.debug("rapyutaio proxy grains_refresh() called...")
	DETAILS["grains_cache"] = None
	return grains()


def fns():
	return {
		"details": "This key is here because a function in "
		"grains/rapyutaio.py called fns() here in the proxymodule."
	}


def service_start(name):
	"""
	Start a "service" on the REST server
	"""
	r = salt.utils.http.query(
		DETAILS["url"] + "service/start/" + name, decode_type="json", decode=True
	)
	return r["dict"]


def service_stop(name):
	"""
	Stop a "service" on the REST server
	"""
	r = salt.utils.http.query(
		DETAILS["url"] + "service/stop/" + name, decode_type="json", decode=True
	)
	return r["dict"]


def service_restart(name):
	"""
	Restart a "service" on the REST server
	"""
	r = salt.utils.http.query(
		DETAILS["url"] + "service/restart/" + name, decode_type="json", decode=True
	)
	return r["dict"]


def service_list():
	"""
	List "services" on the REST server
	"""
	log.debug("rapyutaio proxy service_list() called...")

	(project_id, auth_token) = __utils__['rapyutaio.get_config'](None, None)

	try:
		device_id = __opts__["proxy"]["device_id"]
	except KeyError:
		device = __salt__['rapyutaio.get_device'](name=__opts__['id'], device_id=None, project_id=project_id, auth_token=auth_token)
		device_id = device['uuid']

	url = DEVICE_COMMAND_API_PATH
	header_dict = {
		"accept": "application/json",
		"project": project_id,
		"Authorization": "Bearer " + auth_token,
		"Content-Type": "application/json",
	}

	command = {
		"device_ids": [device_id,],
		"cmd": "systemctl list-units --type=service --output=json",
	}

	log.debug(url)
	log.debug(header_dict)
	log.debug(command)

	response = __utils__['http.query'](url=url,
	                                   header_dict=header_dict,
	                                   method="POST",
	                                   data=__utils__['json.dumps'](command),
	                                   status=True)
	log.debug(response)
	if 'error' in response:
		raise CommandExecutionError(
			response['error']
		)
	response_body = __utils__['json.loads'](response['body'])
	return response_body


def service_status(name):
	"""
	Check if a service is running on the REST server
	"""
	return False



def ping():
	"""
	Is the Rapyuta.IO device online?
	"""
	log.debug("rapyutaio proxy ping() called...")

	try:
		device_id = __opts__["proxy"]["device_id"]
	except KeyError:
		device_id = None

	device = __salt__['rapyutaio.get_device'](name=__opts__['id'], device_id=device_id)

	if device['status'] == 'ONLINE':
		log.debug("Device {} is {}".format(device['uuid'], device['status']))
		return True

	return False



def shutdown(opts):
	"""
	For this proxy shutdown is a no-op
	"""
	log.debug("rest_sample proxy shutdown() called...")
