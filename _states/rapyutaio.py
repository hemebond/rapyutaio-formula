# -*- coding: utf-8 -*-
"""
Manage Rapyuta IO Resources
===================

Manage S3 resources. Be aware that this interacts with Amazon's services,
and so may incur charges.

This module uses ``boto3``, which can be installed via package, or pip.

This module accepts explicit AWS credentials but can also utilize
IAM roles assigned to the instance through Instance Profiles. Dynamic
credentials are then automatically obtained from AWS API and no further
configuration is necessary. More information available `here
<http://docs.aws.amazon.com/AWSEC2/latest/UserGuide/iam-roles-for-amazon-ec2.html>`_.

If IAM roles are not used you need to specify them either in a pillar file or
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
import copy
import difflib
import logging
from pprint import pformat

# Import Salt libs
import salt.ext.six as six
import salt.utils.hashutils
import salt.utils.dictdiffer
import salt.utils.listdiffer
import salt.utils.yaml

log = logging.getLogger(__name__)



__virtual_name__ = "rapyutaio"
def __virtual__():
	"""
	Only load if rapyutaio is available.
	"""
	if "rapyutaio.list_packages" not in __salt__:
		return (False, "rapyutaio module could not be loaded")
	return __virtual_name__



def _get_existing_manifest(name, version):
	"""
	Return the package manifest of an existing package version.
	Returns None if the package and version does not exist
	"""
	try:
		package_summary = __salt__['rapyutaio.get_packages'](name=name,
		                                                     version=version)[0]
	except IndexError as e:
		# There is no existing package with that name and version
		return None

	package_manifest = __salt__['rapyutaio.get_manifest'](package_summary['id'])
	return package_manifest



def package_present(name,
                    source=None,
                    content=None,
                    show_changes=True):
	ret = {
		"name": name,
		"result": False,
		"changes": {},
		"comment": ""
	}

	#
	# Get the content of the new manifest
	#
	if content is None:
		file_name = __salt__["cp.cache_file"](source)

		if file_name is not False:
			with salt.utils.files.fopen(file_name, "r") as _f:
				file_name_part, file_extension = os.path.splitext(file_name)

				log.debug(file_extension)

				if file_extension == '.json':
					new_manifest = salt.utils.json.load(_f)
				elif file_extension in ['.yaml', '.yml']:
					new_manifest = salt.utils.yaml.load(_f)
				else:
					ret['comment'] = "Manifest source must be a JSON (.json) or YAML (.yaml, .yml) file"
					ret['result'] = False
					return ret
		else:
			ret['comment'] = "Source file '{}' missing".format(source)
			ret['result'] = False
			return ret
	else:
		new_manifest = content

	man_name = new_manifest['name']
	man_version = new_manifest['packageVersion']

	#
	# Fetch the existing/old manifest if it exists
	#
	try:
		old_package_info = __salt__['rapyutaio.get_packages'](name=man_name,
		                                                      version=man_version)[0]
	except IndexError as e:
		# There is no existing package with that name and version
		old_manifest = None
	else:
		old_manifest = __salt__['rapyutaio.get_manifest'](old_package_info['id'])
		old_package_uid = old_package_info['id']

	if old_manifest is not None:
		# Is the new manifest different to the old
		ret['changes'] = __utils__['data.recursive_diff'](old_manifest, new_manifest)

		if not ret['changes']:
			# The manifest is already in the correct state so return immediately
			ret['result'] = True
			ret['comment'] = "Package '{} {}' is in the correct state".format(man_name, man_version)
			ret['changes'] = {}
			return ret

	#
	# Find out what changes would be made
	#
	if __opts__['test']:
		# Always return a None result for dry-runs
		ret['result'] = None

		if old_manifest is not None:
			if ret['changes']:
				ret['comment'] = "Package '{} {}' would be updated".format(man_name, man_version)

				if not show_changes:
					ret['changes'] = "<show_changes=False>"
		else:
			ret['comment'] = "New package '{} {}' would be created".format(man_name, man_version)
			ret['changes'] = {
				'new': content
			}

		return ret

	#
	# Delete the existing manifest if it exists and is different to the new manifest
	#
	if old_manifest is not None:
		if ret['changes']:
			delete_response = __salt__['rapyutaio.delete_package'](old_package_uid)

			if delete_response['result'] is False:
				ret['comment'] = delete_response['message']
				return ret
		else:
			ret['comment'] = "Package '{} {}' is in the correct state".format(man_name, man_version)

	#
	# Attempt to upload the new manifest
	#
	response = __salt__['rapyutaio.create_or_update_package'](content=new_manifest,
	                                                          dry_run=__opts__['test'])
	log.debug(response)

	if response['result'] == False:
		# Failed to upload the new manifest
		ret['comment'] = response['message']
	else:
		ret['result'] = True

		if old_manifest is not None:
			# Replacing existing manifest
			ret['comment'] = "Package '{} {}' was updated".format(man_name, man_version)
		else:
			# Creating new manifest
			ret['changes'] = response['changes']
			ret['comment'] = "New package '{} {}' created".format(man_name, man_version)

	return ret



def package_absent():
	pass



def network_present():
	pass



def network_absent():
	pass



def volume_present():
	pass



def volume_attached():
	pass



def volume_absent():
	pass



def diff_manifests(oldpkg, newpkg):
	"""
	Find the difference between a new manifest and an existing manifest returned from the API
	"""
	changes = {
		'old': {},
		'new': {},
	}

	#
	# Package
	#
	pkg_vars = [
		"apiVersion",
		"bindable",
		"description",
		"name",
		"packageVersion",
	]
	for v in pkg_vars:
		# manifest has "name" but the API packageInfo has "packageName"
		if v == "name":
			o = oldpkg['packageName']
		else:
			o = oldpkg[v]
		n = newpkg[v]

		if o != n:
			changes['old'][v] = o
			changes['new'][v] = n


	#
	# Plans
	#
	# "dependentDeployments": [],
	# "exposedParameters": [],
	# "inboundROSInterfaces": {
	# "anyIncomingScopedOrTargetedRosConfig": false
	# },
	# "includePackages": [],
	# "metadata": {},
	# "name": "default",
	# "singleton": false

	#
	# Components
	#
	# package -> plans[0] -> components[] == package -> plans[0] -> components -> components[]

	return changes
