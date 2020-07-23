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
	# Find out what changes would be made
	#
	if __opts__['test']:
		# Always return a None result for dry-runs
		ret['result'] = None

		# Get the content of the new manifest
		if content is None:
			file_name = __salt__["cp.cache_file"](source)

			if os.path.exists(file_name):
				with salt.utils.files.fopen(file_name, "r") as _f:
					new_manifest = salt.utils.json.load(_f)
		else:
			new_manifest = content

		new_manifest['name'] = name
		version = new_manifest['packageVersion']

		# Fetch the existing/old manifest if it exists
		old_manifest = _get_existing_manifest(new_manifest['name'], new_manifest['packageVersion'])

		if old_manifest:
			# diff = __utils__['dictdiffer.deep_diff'](old_manifest, new_manifest)
			# ret['changes'] = diff

			diff = __utils__['dictdiffer.recursive_diff'](old_manifest, new_manifest)
			ret['changes'] = diff.diffs


			if ret['changes']:
				ret['comment'] = "Package '{} {}' would be updated".format(name, version)

				if not show_changes:
					ret['changes'] = "<show_changes=False>"
			else:
				ret['comment'] = "Package '{} {}' is in the correct state".format(name, version)
				ret['changes'] = {}
		else:
			ret['comment'] = "New package '{} {}' would be created".format(name, version)
			ret['changes'] = {
				'new': content
			}

		return ret

	#
	# Attempt to upload the new manifest
	#
	response = __salt__['rapyutaio.create_or_update_package'](name=name,
	                                                          source=source,
	                                                          content=content,
	                                                          dry_run=__opts__['test'])
	log.debug(response)

	if response['status'] == 409:
		# Conflict: package already exists with this version number
		file_name = __salt__["cp.cache_file"](source)

		if os.path.exists(file_name):
			with salt.utils.files.fopen(file_name, "r") as _f:
				new_manifest = salt.utils.json.load(_f)

		new_manifest['name'] = name

		existing_package_summary = __salt__['rapyutaio.get_packages'](name=new_manifest['name'],
		                                                              version=new_manifest['packageVersion'])[0]
		package_uid = existing_package_summary['id']
		old_manifest = __salt__['rapyutaio.get_manifest'](package_uid=package_uid)

		diff = __utils__['dictdiffer.deep_diff'](old_manifest, new_manifest)
		ret['changes'] = diff

		if diff != {}:
			delete_response = __salt__['rapyutaio.delete_package'](package_uid)

			if delete_response['status'] == 200:
				create_info = __salt__['rapyutaio.create_or_update_package'](name=name, contents=new_manifest)

				if 'error' in create_info:
					ret['comment'] = create_info['message']
				else:
					ret['result'] = True
	elif response['status'] == 201:
		ret['result'] = True
		ret['changes'] = salt.utils.json.loads(response['body'])
	else:
		ret['comment'] = response

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
