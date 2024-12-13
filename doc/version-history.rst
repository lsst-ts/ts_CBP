===============
Version History
===============

.. towncrier release notes start

ts_cbp v1.5.0 (2024-12-13)
==========================

Features
--------

- Add retry loop to client for improved responseness under spotty connections. (`DM-47555 <https://rubinobs.atlassian.net/DM-47555>`_)
- Set azimuth and elevation to false at the same time during move command to publish one less inPosition event. (`DM-47555 <https://rubinobs.atlassian.net/DM-47555>`_)


Bugfixes
--------

- Remove colon from reply. (`DM-47349 <https://rubinobs.atlassian.net/DM-47349>`_)
- Set the target event with current positions before starting telemetry loop to avoid inPosition not being set properly. (`DM-47555 <https://rubinobs.atlassian.net/DM-47555>`_)
- Go to fault state if connect call failed. (`DM-47555 <https://rubinobs.atlassian.net/DM-47555>`_)
- Set component host to simulator host when in simulation mode. (`DM-47555 <https://rubinobs.atlassian.net/DM-47555>`_)
- Modified the inPosition calculation for mask rotation to deal with 0 and 360. Also increased the timeout for the mask change. (`DM-47638 <https://rubinobs.atlassian.net/DM-47638>`_)


ts_cbp v1.4.1 (2024-05-31)
==========================

Bugfixes
--------

- Add noarch to Jenkinsfile.conda. (`DM-44417 <https://rubinobs.atlassian.net/DM-44417>`_)
- Fix two unit tests. (`DM-44417 <https://rubinobs.atlassian.net/DM-44417>`_)


ts_cbp v1.4.0 (2024-05-27)
==========================

Features
--------

- Add maskRotation command. (`DM-42249 <https://rubinobs.atlassian.net/DM-42249>`_)


Bugfixes
--------

- Update ts-conda-build to 0.4. (`DM-43486 <https://rubinobs.atlassian.net/DM-43486>`_)


Improved Documentation
----------------------

- Add towncrier support. (`DM-43486 <https://rubinobs.atlassian.net/DM-43486>`_)


v1.3.0
======
* Use tcpip client class
* Add missing license headers

v1.2.1
======
* Add ts_pre_commit_conf file
* Use named parameters in CondaPipeline

v1.2.0
======
* Update precommit to black 23, isort 5.12 & check-yaml 4.4.
* Move config_schema to root namespace.
* Fix connect_callback async warning.
* Merge cli module into csc module.
* Modernize conda recipe.

v1.1.0
======

* Update to salobj 7

v1.0.0
======

* CSC added
* Documentation added
* ``Black`` linting support added
* Basic simulator support
* Added target event
* Added inPosition event
* Upgrade to black 20.8

