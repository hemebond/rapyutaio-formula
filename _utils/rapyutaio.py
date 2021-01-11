import salt.config
import salt.utils.sdb
from datetime import datetime
import copy
import logging
from collections.abc import Mapping
from salt.matchers.compound_match import match as salt_compound_match
from salt.exceptions import CommandExecutionError, InvalidConfigError



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
	if not project_id and __salt__['config.get']("rapyutaio:project_id"):
		project_id = __salt__['config.get']("rapyutaio:project_id")

	if not auth_token and __salt__['config.get']("rapyutaio:auth_token"):
		auth_token = __salt__['config.get']("rapyutaio:auth_token")

	return (project_id, auth_token)



def get_credentials():
	config = __salt__['config.get']('rapyutaio')
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
	}



def _send_request(url, header_dict={}, method="GET", data=None, params=None):
	"""
	Sends an HTTP request, parses the result, raises an exception on error
	"""
	log.debug("url: %s" % url)
	log.debug("header_dict: %s" % header_dict)
	log.debug("method: %s" % method)
	log.debug("data: %s" % data)
	log.debug("params: %s" % params)

	if data is not None:
		header_dict['Content-Type'] = "application/json"

	response = salt.utils.http.query(url=url,
	                                 header_dict=header_dict,
	                                 method=method,
	                                 data=salt.utils.json.dumps(data) if data is not None else None,
	                                 params=params,
	                                 status=True)
	log.debug(response)

	if 'error' in response:
		raise CommandExecutionError(
			message=response['error'],
			info={
				"status": int(response['status'])
			}
		)

	if response['body'] != '':
		return salt.utils.json.loads(response['body'])
	else:
		return {}



def api_request(url,
                http_method="GET",
                header_dict={},
                data=None,
                params=None,
                project_id=None,
                auth_token=None):
	"""
	Wrapper for HTTP requests to IO and handle authentication and tokens
	"""
	log.debug("rapyutaio.api_request() called...")
	project_id = project_id or __salt__['config.get']("rapyutaio:project_id")

	if not project_id:
		raise InvalidConfigError("No rapyutaio project_id found")

	generated_auth_token = None

	if auth_token is None:
		# Get the cached token with its expiryAt
		cached_token = salt.utils.sdb.sdb_get('sdb://rapyutaio/auth_token', __opts__, None)

		log.debug("cached_token: {}".format(str(cached_token)))

		if cached_token:
			try:
				# Trim off the nanoseconds when parsing the datetime
				expiry = datetime.strptime(cached_token['expiryAt'][:19], '%Y-%m-%dT%H:%M:%S')

				if expiry >= datetime.utcnow():
					generated_auth_token = cached_token['token']
			except KeyError:
				pass

	if auth_token is None and generated_auth_token is None:
		# cached token has expired
		generated_auth_token = _renew_token()['token']

	header_dict = _header_dict(project_id, auth_token or generated_auth_token)

	# first request attempt
	try:
		return _send_request(url=url,
		                     header_dict=header_dict,
		                     method=http_method,
		                     data=data,
		                     params=params)
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
				                     method=http_method,
				                     data=data,
				                     params=params)
		raise e



def deep_merge(tgt, src):
	"""Deep merge tgt dict with src
	For each k,v in src: if k doesn't exist in tgt, it is deep copied from
	src to tgt. Otherwise, if v is a list, tgt[k] is replaced with
	src[k]. If v is a set, tgt[k] is updated with v, If v is a dict,
	recursively deep-update it.

	Examples:
	>>> t = {'name': 'Ferry', 'hobbies': ['programming', 'sci-fi']}
	>>> print deep_merge(t, {'hobbies': ['gaming']})
	{'name': 'Ferry', 'hobbies': ['gaming', 'sci-fi']}
	"""
	if isinstance(tgt, Mapping):
		for sk, sv in src.items():
			if sk[-1] == "+":
				merge_sublists = True
				tk = sk[:-1]
			elif sk[-1] == "-":
				replace_sublists = True
				tk = sk[:-1]
			else:
				merge_sublists = False
				replace_sublists = False
				tk = sk

			tv = tgt.get(tk, None)

			if isinstance(tv, Mapping) and isinstance(sv, Mapping):
				if sk in tgt:
					tgt[tk] = deep_merge(tgt[tk], sv)
				else:
					tgt[tk] = copy.deepcopy(sv)
			elif isinstance(tv, list) and isinstance(sv, list):
				if merge_sublists:
					tgt[tk].extend([x for x in sv if x not in tv])
				elif replace_sublists:
					tgt[tk] = sv
				else:
					tgt[tk] = deep_merge(tv, sv)
			elif isinstance(tv, set) and isinstance(sv, set):
				if sk in tgt:
					tgt[tk].update(sv.copy())
				else:
					tgt[tk] = sv.copy()
			else:
				tgt[tk] = copy.copy(sv)
	elif isinstance(tgt, list):
		tgt_len = len(tgt)

		for idx in range(len(src)):
			if src[idx] in (None, "", [], {}):
				continue

			if idx < tgt_len:
				if isinstance(tgt[idx], (Mapping, list)) and isinstance(src[idx], (Mapping, list)):
					tgt[idx] = deep_merge(tgt[idx], src[idx])
				else:
					tgt[idx] = src[idx]
			else:
				tgt.append(src[idx])
	else:
		return src

	return tgt
