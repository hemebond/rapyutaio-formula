# -*- coding: utf-8 -*-
"""
This is a simple proxy-minion designed to connect to and
communicate with the Rapyuta.IO web service

Run a standalone proxy-minion as a non-root user:

	$ salt-proxy --proxyid=myproxy \
	             --config-dir=/srv/proxy \
	             --pid-file=/srv/proxy/myproxy.pid \
	             --log-level=debug
"""
import logging
from salt.exceptions import CommandExecutionError



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

ORG_API_PATH = CORE_API_HOST + "/api/organization/{org_id}/get"
USER_API_PATH = CORE_API_HOST + "/api/user/me/get"

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
	log.debug("rapyutaio proxy __virtual__() called...")
	return True



def init(opts):
	"""
	Every proxy module needs an 'init', though you can
	just put DETAILS['initialized'] = True here if nothing
	else needs to be done.
	"""
	log.debug("rapyutaio proxy init() called...")
	DETAILS["initialized"] = True
	return True



def alive(opts):
	"""
	This function returns a flag with the connection state.
	It is very useful when the proxy minion establishes the communication
	via a channel that requires a more elaborated keep-alive mechanism, e.g.
	NETCONF over SSH.
	"""
	return ping()



def initialized():
	"""
	Since grains are loaded in many different places and some of those
	places occur before the proxy can be initialized, return whether
	our init() function has been called
	"""
	log.debug("rapyutaio proxy initialized() called...")
	return DETAILS.get("initialized", False)



def grains():
	"""
	Get the grains from the proxied device
	"""
	log.debug("rapyutaio proxy grains() called...")
	global GRAINS_CACHE
	if not GRAINS_CACHE:
		grains = __utils__['rapyutaio.api_request'](USER_API_PATH)

		org_id = grains['organization']['guid']
		grains['organization'] = __utils__['rapyutaio.api_request'](ORG_API_PATH.format(org_id=org_id))

		GRAINS_CACHE = grains

	return {'rapyutaio': GRAINS_CACHE}



def grains_refresh():
	"""
	Refresh the grains from the proxied device
	"""
	log.debug("rapyutaio proxy grains_refresh() called...")
	DETAILS["grains_cache"] = None
	return grains()



def ping():
	"""
	Is the Rapyuta.IO online?
	"""
	log.debug("rapyutaio proxy ping() called...")

	header_dict = {
		"Access-Control-Request-Method": "GET",
		"Access-Control-Request-Headers": "authorization,project",
	}
	try:
		__utils__['rapyutaio.api_request'](url=USER_API_PATH,
		                                   http_method="OPTIONS",
		                                   header_dict=header_dict)
	except CommandExecutionError:
		return False

	return True



def shutdown(opts):
	"""
	For this proxy shutdown is a no-op
	"""
	log.debug("rapyutaio proxy shutdown() called...")
