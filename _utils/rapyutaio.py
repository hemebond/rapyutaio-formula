import salt.config
from salt.matchers.compound_match import match as salt_compound_match


__salt__ = None



CATALOG_HOST = "https://gacatalog.apps.rapyuta.io"
PROVISION_API_PATH = CATALOG_HOST + "/v2/service_instances"

CORE_API_HOST = "https://gaapiserver.apps.rapyuta.io"
DEVICE_API_BASE_PATH = CORE_API_HOST + "/api/device-manager/v0/"
DEVICE_API_PATH = DEVICE_API_BASE_PATH + "devices/"
DEVICE_COMMAND_API_PATH = DEVICE_API_BASE_PATH + 'cmd/'
DEVICE_METRIC_API_PATH = DEVICE_API_BASE_PATH + 'metrics/'
DEVICE_TOPIC_API_PATH = DEVICE_API_BASE_PATH + 'topics/'



def __virtual__():
	"""
	Load as a different name
	"""
	global __salt__
	if __salt__ is None:
		__salt__ = salt.loader.minion_mods(__opts__)
	return True

TESTVAL = "Hello"


def test():
	return TESTVAL



def get_config(project_id, auth_token):
	"""
	If there is no project_id or auth token provided, this
	will attempt to fetch it from the Salt configuration
	"""
	if not project_id and __salt__['config.option']("rapyutaio.project_id"):
		project_id = __salt__['config.option']("rapyutaio.project_id")

	if not auth_token and __salt__['config.option']("rapyutaio.auth_token"):
		auth_token = __salt__['config.option']("rapyutaio.auth_token")

	return (project_id, auth_token)



def match(tgt, device):
	"""
	Matches devices against a compound target string using the
	device name as the id and device labels as the grains
	"""
	opts = __opts__

	opts.update({
		"id": device['name'],
		"grains": {
			"labels": {
				label['key']: label['value'] for label in device['labels']
			},
			"config_variables": {
				var['key']: var['value'] for var in device['config_variables']
			},
			"status": device['status']
		}
	})

	return salt_compound_match(tgt, opts)
