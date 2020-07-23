.. _readme:

rapyutaio-formula
================

A SaltStack formula for managing a Rapyuta IO project.

.. contents:: **Table of Contents**
   :depth: 1

General notes
-------------

See the full `SaltStack Formulas installation and usage instructions
<https://docs.saltstack.com/en/latest/topics/development/conventions/formulas.html>`_.

If you are interested in writing or contributing to formulas, please pay attention to the `Writing Formula Section
<https://docs.saltstack.com/en/latest/topics/development/conventions/formulas.html#writing-formulas>`_.

If you want to use this formula, please pay attention to the ``FORMULA`` file and/or ``git tag``,
which contains the currently released version. This formula is versioned according to `Semantic Versioning <http://semver.org/>`_.

See `Formula Versioning Section <https://docs.saltstack.com/en/latest/topics/development/conventions/formulas.html#versioning>`_ for more details.

If you need (non-default) configuration, please pay attention to the ``pillar.example`` file and/or `Special notes`_ section.

Contributing to this repo
-------------------------

**Commit message formatting is significant!!**

Please see `How to contribute <https://github.com/saltstack-formulas/.github/blob/master/CONTRIBUTING.rst>`_ for more details.

Special notes
-------------

None

Available states
----------------

.. contents::
   :local:

``rapyutaio``
^^^^^^^^^^^^

*Meta-state (This is a state that includes other states)*.

This installs the rapyutaio package,
manages the rapyutaio configuration file and then
starts the associated rapyutaio service.

``rapyutaio.package``
^^^^^^^^^^^^^^^^^^^^

This state will install the rapyutaio package only.

``rapyutaio.config``
^^^^^^^^^^^^^^^^^^^

This state will configure the rapyutaio service and has a dependency on ``rapyutaio.install``
via include list.

``rapyutaio.service``
^^^^^^^^^^^^^^^^^^^^

This state will start the rapyutaio service and has a dependency on ``rapyutaio.config``
via include list.

``rapyutaio.clean``
^^^^^^^^^^^^^^^^^^

*Meta-state (This is a state that includes other states)*.

this state will undo everything performed in the ``rapyutaio`` meta-state in reverse order, i.e.
stops the service,
removes the configuration file and
then uninstalls the package.

``rapyutaio.service.clean``
^^^^^^^^^^^^^^^^^^^^^^^^^^

This state will stop the rapyutaio service and disable it at boot time.

``rapyutaio.config.clean``
^^^^^^^^^^^^^^^^^^^^^^^^^

This state will remove the configuration of the rapyutaio service and has a
dependency on ``rapyutaio.service.clean`` via include list.

``rapyutaio.package.clean``
^^^^^^^^^^^^^^^^^^^^^^^^^^

This state will remove the rapyutaio package and has a depency on
``rapyutaio.config.clean`` via include list.

``rapyutaio.subcomponent``
^^^^^^^^^^^^^^^^^^^^^^^^^

*Meta-state (This is a state that includes other states)*.

This state installs a subcomponent configuration file before
configuring and starting the rapyutaio service.

``rapyutaio.subcomponent.config``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

This state will configure the rapyutaio subcomponent and has a
dependency on ``rapyutaio.config`` via include list.

``rapyutaio.subcomponent.config.clean``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

This state will remove the configuration of the rapyutaio subcomponent
and reload the rapyutaio service by a dependency on
``rapyutaio.service.running`` via include list and ``watch_in``
requisite.
