# -*- coding: utf-8 -*-
"""
Manage Rapyuta IO Resources
===================

Manage Rapyuta IO resources.

Specify credentials either in a pillar file or
in the minion's config file:

.. code-block:: yaml

	rapyutaio.project_id: project-oidjfiasuhgw4hgfw4thw0hg
	rapyutaio.auth_token: jr234ny2u5yb34u52y0b5y234785ycn45y603485


It's also possible to specify ``project_id``, and ``auth_token`` via a profile,
either passed in as a dict, or as a string to pull from pillars or minion
config:

.. code-block:: yaml

	myprofile:
		project_id: project-oidjfiasuhgw4hgfw4thw0hg
		auth_token: jr234ny2u5yb34u52y0b5y234785ycn45y603485

.. code-block:: yaml

	Ensure IO package exists:
		rapyutaio.package_present:
			- name: grafana
			- source: /path/to/local/file
			- region: us-east-1
			- project_id: project-oidjfiasuhgw4hgfw4thw0hg
			- auth_token: jr234ny2u5yb34u52y0b5y234785ycn45y603485
			- profile: myprofile
"""

# Import Python Libs
from __future__ import absolute_import, print_function, unicode_literals

import os
import logging

from salt.exceptions import CommandExecutionError
# from salt.exceptions import CommandExecutionError, SaltInvocationError

log = logging.getLogger(__name__)



__virtual_name__ = "rapyutaio"
def __virtual__():
	"""
	Only load if rapyutaio is available.
	"""
	if "rapyutaio.get_packages" not in __salt__:
		return (False, "rapyutaio module could not be loaded")
	return __virtual_name__



# -----------------------------------------------------------------------------
#
# Packages
#
# -----------------------------------------------------------------------------
def package_present(name,
                    source=None,
                    manifest=None,
                    show_changes=True):
	"""
	"""
	ret = {
		"name": name,
		"result": False,
		"changes": {},
		"comment": ""
	}

	#
	# Get the content of the new manifest
	#
	if manifest is None:
		if source is None:
			ret['comment'] = "package_present requires either 'source' or 'manifest'"
			return ret

		file_name = __salt__["cp.cache_file"](source)

		if file_name is not False:
			with __utils__['files.fopen'](file_name, "r") as _f:
				file_name_part, file_extension = os.path.splitext(file_name)

				if file_extension == '.json':
					new_manifest = __utils__['json.load'](_f)
				elif file_extension in ['.yaml', '.yml']:
					new_manifest = __utils__['yaml.load'](_f)
				else:
					ret['comment'] = "Manifest source must be a JSON (.json) or YAML (.yaml, .yml) file"
					return ret
		else:
			ret['comment'] = "Source file '{}' missing".format(source)
			return ret
	else:
		new_manifest = manifest

	#
	# Allow setting the name via the state
	#
	if 'name' not in new_manifest:
		new_manifest['name'] = name

	man_name = new_manifest['name']
	man_version = new_manifest['packageVersion']

	#
	# Fetch the existing/old manifest if it exists
	#
	try:
		old_package = __salt__['rapyutaio.get_package'](name=man_name,
		                                                version=man_version)
	except CommandExecutionError as e:
		ret['comment'] = e
		return ret

	if old_package:
		old_package_uid = old_package['packageInfo']['guid']
		old_manifest = __salt__['rapyutaio.get_manifest'](guid=old_package_uid)
	else:
		old_manifest = {}

	if old_manifest:
		# Is the new manifest different to the old
		ret['changes'] = __utils__['data.recursive_diff'](old_manifest, new_manifest)

		if not ret['changes']:
			# The manifest is already in the correct state so return immediately
			ret['result'] = True
			ret['comment'] = "Package '{} {}' is in the correct state".format(man_name, man_version)
			return ret

	#
	# Test
	#
	if __opts__['test']:
		# Always return a None result for dry-runs
		ret['result'] = None

		if ret['changes']:
			ret['comment'] = "Package '{} {}' would be updated".format(man_name, man_version)

		else:
			ret['comment'] = "New package '{} {}' would be created".format(man_name, man_version)
			ret['changes'] = {
				'new': new_manifest,
				'old': old_manifest
			}

		if not show_changes:
			ret['changes'] = "<show_changes=False>"

		return ret

	# TODO: Create a "clean" manifest from the remote/existing manifest that only contains keys
	# that we know are required or will be used and compare only those

	#
	# Delete the existing manifest if it exists and is different to the new manifest
	#
	if old_manifest is not None:
		if not ret['changes']:
			ret['comment'] = "Package '{} {}' is in the correct state".format(man_name, man_version)
			ret['result'] = True
			return ret

		# First check that the package is not in use
		pkg_deployments = __salt__['rapyutaio.get_deployments'](package_uid=old_package_uid)
		if pkg_deployments != []:
			ret['comment'] = "Package '{} {}' is in use and can't be updated.".format(man_name, man_version)
			return ret

		try:
			__salt__['rapyutaio.delete_package'](guid=old_package_uid)
		except CommandExecutionError as e:
			ret['comment'] = e
			return ret

	#
	# Attempt to upload the new manifest
	#
	response = __salt__['rapyutaio.create_package'](manifest=new_manifest)

	ret['result'] = True

	if old_manifest is not None:
		# Replacing existing manifest
		ret['comment'] = "Package '{} {}' was updated".format(man_name, man_version)
	else:
		# Creating new manifest
		ret['changes'] = response
		ret['comment'] = "New package '{} {}' created".format(man_name, man_version)

	return ret



def package_absent(name, version):
	"""
	Removes the version of a package if it exists.
	"""
	ret = {
		"name": name,
		"result": False,
		"comment": "",
		"changes": {},
	}

	try:
		package = __salt__['rapyutaio.get_package'](name=name, version=version)
	except CommandExecutionError as e:
		ret['comment'] = e
		return ret

	if not package:
		ret['result'] = True
		ret['comment'] = "Package '{0} {1}' is not present".format(name, version)
		return ret

	#
	# test=True
	#
	if __opts__['test']:
		# Always return a None result for dry-runs
		ret['result'] = None
		ret['comment'] = "Package '{0} {1}' would be deleted".format(name, version)
		return ret

	try:
		__salt__['rapyutaio.delete_package'](name=name, version=version)
	except CommandExecutionError as e:
		ret['comment'] = e
		return ret

	ret['result'] = True
	ret['changes']['old'] = package
	ret['changes']['new'] = None
	ret['comment'] = "Package {0} {1} deleted".format(name, version)

	return ret



# -----------------------------------------------------------------------------
#
# Networks
#
# -----------------------------------------------------------------------------
def network_present(name,
                    runtime,
                    ros_distro,
                    parameters=None):
	"""
	"""
	ret = {
		"name": name,
		"result": False,
		"comment": "",
		"changes": {},
	}

	old_network = __salt__['rapyutaio.get_network'](name=name)

	new_network = {
		"name": name,
		"runtime": runtime,
		"rosDistro": ros_distro,
		"parameters": parameters or {},
	}

	if old_network:
		log.debug(old_network)
		ret['changes'] = __utils__['data.recursive_diff'](
			{
				"name": old_network['name'],
				"runtime": old_network['runtime'],
				"rosDistro": old_network['rosDistro'],
				"parameters": old_network.get('parameters', {}),
			},
			new_network
		)

		if ret['changes']:
			ret['result'] = False
			ret['comment'] = "Network '{0}' exists but is different.".format(name)
		else:
			ret['result'] = True
			ret['comment'] = "Network '{0}' is in the correct state.".format(name)

		return ret

	if __opts__['test']:
		# Always return a None result for dry-runs
		ret['result'] = None
		ret['comment'] = "Network '{0}' would be created.".format(name)
		ret['changes']['old'] = {}
		ret['changes']['new'] = new_network
		return ret

	response = __salt__['rapyutaio.create_network'](name=name,
	                                                runtime=runtime,
	                                                ros_distro=ros_distro,
	                                                parameters=parameters)

	ret['result'] = True
	ret['comment'] = "New network {0} created".format(name)
	ret['changes'] = response

	return ret




def network_absent(name):
	ret = {
		"name": name,
		"result": False,
		"comment": "",
		"changes": {},
	}

	old_network = __salt__['rapyutaio.get_network'](name=name)

	if not old_network:
		ret['result'] = True
		ret['comment'] = "Network {0} is not present".format(name)
		return ret

	old_network_guid = old_network['guid']

	ret['changes'] = {
		'old': old_network,
		'new': None
	}

	#
	# test=True
	#
	if __opts__['test']:
		# Always return a None result for dry-runs
		ret['result'] = None
		ret['comment'] = "Network {0} would be deleted".format(name)
		return ret

	__salt__['rapyutaio.delete_network'](guid=old_network_guid)

	ret['result'] = True
	ret['comment'] = "Network {0} deleted".format(name)
	return ret



# -----------------------------------------------------------------------------
#
# Volumes
#
# -----------------------------------------------------------------------------
def volume_present():
	pass



def volume_attached():
	pass



def volume_absent():
	pass



# -----------------------------------------------------------------------------
#
# Deployments
#
# -----------------------------------------------------------------------------
def deployment_present(name,
                       package_name,
                       package_version,
                       parameters={},
                       dependencies=[]):
	ret = {
		"name": name,
		"result": False,
		"comment": "",
		"changes": {},
	}

	existing_deployment = __salt__['rapyutaio.get_deployment'](name=name)

	if existing_deployment is not None:
		pkg_id = existing_deployment['packageId']
		existing_dpl_pkg = __salt__['rapyutaio.get_package'](name=package_name,
		                                                     version=package_version)
		log.fatal(existing_dpl_pkg)
		if pkg_id == existing_dpl_pkg['packageInfo']['guid']:
			ret['result'] = True
			ret['comment'] = "Deployment {} of package {}:{} already exists".format(name, package_name, package_version)
			return ret

		log.fatal(existing_deployment)
		# for component in existing_deployment

		# ret['changes'] = __utils__['data.recursive_diff'](existing_deployment, new_manifest)

	#
	# TODO: check the properties of the deployment
	# to make sure the deployment parameters are the same
	#

	if __opts__['test']:
		ret['result'] = None

		if existing_deployment:
			ret['comment'] = "Deployment '{0}' already exists".format(name)
		else:
			ret['comment'] = "Deployment '{0}' would be created".format(name)

		return ret

	try:
		deployment = __salt__['rapyutaio.create_deployment'](name=name,
		                                                     package_name=package_name,
		                                                     package_version=package_version,
		                                                     parameters=parameters,
		                                                     dependencies=dependencies)
	except CommandExecutionError as e:
		ret['result'] = False
		ret['comment'] = str(e)
		return ret

	ret['result'] = True
	ret['changes']['new'] = name
	ret['comment'] = "Deployment '{0}' created".format(name)
	return ret



def deployment_absent(name):
	ret = {
		"name": name,
		"result": False,
		"comment": "",
		"changes": {},
	}

	existing_deployment = __salt__['rapyutaio.get_deployment'](name=name)

	if not existing_deployment:
		ret['result'] = True
		ret['comment'] = "Deployment '{0}' is not present".format(name)
		return ret

	if __opts__['test']:
		ret['result'] = None
		ret['comment'] = "Deployment '{0}' would be removed".format(name)
		return ret

	response = __salt__['rapyutaio.delete_deployment'](name=name)

	ret['result'] = True
	ret['changes']['removed'] = name
	ret['comment'] = "Deployment '{0}' removed".format(name)
	return ret
