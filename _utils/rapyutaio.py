import salt.config
import salt.utils.sdb
from datetime import datetime
import logging
from salt.matchers.compound_match import match as salt_compound_match
from salt.exceptions import CommandExecutionError, SaltInvocationError



__salt__ = None



log = logging.getLogger(__name__)



LOGIN_URL = 'https://garip.apps.rapyuta.io/user/login?type=high'

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



def get_credentials():
	config = __salt__['config.option']('rapyutaio')
	return (config['username'], config['password'])



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



def get_auth_token(username, password):
	"""
	Use the username (email) and password to authenticate to rapyuta.io and
	generate a new JWT auth token.

	Cache the token in the minion Salt cache so it can be
	re-used without having to re-authenticate or generate a new one
	each time we use an execution module or apply states.

	A token is valid across all the projects the user has access to.
	"""
	header_dict = {
		"accept": "application/json",
		"Content-Type": "application/json",
	}
	data = {
		"email": username,
		"password": password,
	}
	log.debug(salt.utils.json.dumps(data))
	response = salt.utils.http.query(url='https://garip.apps.rapyuta.io/user/login?type=high',
	                                 header_dict=header_dict,
	                                 method="POST",
	                                 data=salt.utils.json.dumps(data),
	                                 status=True)
	log.debug(response)

	if 'error' in response:
		raise CommandExecutionError(
			response['error']
		)

	response_body = salt.utils.json.loads(response['body'])
	response_data = response_body['data']

	salt.utils.sdb.sdb_set("sdb://rapyutaio/auth_token", response_data, __opts__, None)

	return response_data



def _renew_token():
	"""
	Login to rapyuta.io using credentials in the minion config

	rapyutaio:
	  username: "first.last@email.com"
	  password: "mypassword"
	"""
	username, password = get_credentials()
	return get_auth_token(username, password)



def _header_dict(project_id, auth_token):
	"""
	Create a header dict from the project ID and auth token
	"""
	return {
		"accept": "application/json",
		"project": str(project_id),
		"Authorization": "Bearer " + str(auth_token),
		"Content-Type": "application/json",
	}



def _send_request(url, header_dict={}, method="GET", data=None):
	"""
	Sends an HTTP request, parses the result, raises an exception on error
	"""
	log.debug("url: %s" % url)
	log.debug("header_dict: %s" % header_dict)
	log.debug("method: %s" % method)
	log.debug("data: %s" % data)

	response = salt.utils.http.query(url=url,
	                                 header_dict=header_dict,
	                                 method=method,
	                                 data=salt.utils.json.dumps(data) if data is not None else None,
	                                 status=True)
	log.debug(response)

	if 'error' in response:
		raise CommandExecutionError(
			message=response['error'],
			info={
				"status": int(response['status'])
			}
		)

	response_body = salt.utils.json.loads(response['body'])
	log.debug(response_body)

	return response_body



def api_request(url, header_dict={}, method="GET", data=None, project_id=None, auth_token=None):
	"""
	Wrapper for HTTP requests to IO and handle authentication and tokens
	"""
	project_id = project_id or __salt__['config.option']("rapyutaio.project_id")

	if auth_token is None:
		# Get the cached token with its expiryAt
		cached_token = salt.utils.sdb.sdb_get('sdb://rapyutaio/auth_token', __opts__, None)

		# Trim off the nanoseconds when parsing the datetime
		expiry = datetime.strptime(cached_token['expiryAt'][:19], '%Y-%m-%dT%H:%M:%S')
		if expiry < datetime.utcnow():
			# cached token has expired
			generated_auth_token = _renew_token()['token']
		else:
			generated_auth_token = cached_token['token']

	header_dict = _header_dict(project_id, auth_token or generated_auth_token)

	# first request attempt
	try:
		return _send_request(url=url,
		                     header_dict=header_dict,
		                     method=method,
		                     data=data)
	except CommandExecutionError as e:
		if e.info['status'] == 401:
			# HTTP 401: Unauthorized
			if auth_token is None:
				# only generate a new token if the first was
				# generated from a login
				generated_auth_token = _renew_token()['token']
				header_dict = _header_dict(project_id, generated_auth_token)
				return _send_request(url=url,
				                     header_dict=header_dict,
				                     method=method,
				                     data=data)

		raise e
