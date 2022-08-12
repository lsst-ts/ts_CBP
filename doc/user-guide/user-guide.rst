##############
CBP User Guide
##############

The CBP has two directions for axial movement, the azimuth (side-to-side) and altitude (bottom-to-top).
It also allows for up to five masks to be added as a means of characterizing beam projection.
Limits are in place for each axis to prevent damage to the device.
The CBP also has the ability to be parked, where the altitude is at -70 degrees and the motors cannot be moved.
This ability can be manually commanded, but is automatically triggered if an internal battery source detects that the power has been lost for more than ~3 seconds.


.. _user-guide:user-guide:cbp-interface:

CBP Interface
======================

A link to the SAL API can be found at the top of the :doc:`index </index>`.

The main commands that will likely be used are:

    - :ref:`ts_xml:CBP:Commands:move`
    - :ref:`ts_xml:CBP:Commands:changeMask`

The relevant events include:

    - :ref:`ts_xml:CBP:Events:target`
    - :ref:`ts_xml:CBP:Events:inPosition`

The relevant telemetry include:

    - :ref:`ts_xml:CBP:Telemetry:azimuth`
    - :ref:`ts_xml:CBP:Telemetry:elevation`
    - :ref:`ts_xml:CBP:Telemetry:mask`
    - :ref:`ts_xml:CBP:Telemetry:status`

.. _user-guide:user-guide:example-use-case:

Example Use-Case
================

Starting the CSC:

.. code::

    from lsst.ts import salobj

    domain = salobj.Domain()

    cbp = salobj.Remote(name="CBP", domain=domain)

    await cbp.start_task

Un-parking the CSC:

.. code::

    await cbp.cmd_park.set_start(park=False, timeout=10)

When moving the CBP in azimuth and elevation to a desired position, both values must always be provided
The following code snippet demonstrates the command:

.. code::

    await cbp.cmd_move.set_start(azimuth=5, elevation=10, timeout=10)

Moving the CBP in altitude:

.. code::

    await cbp.cmd_moveAltitude.set_start(altitude=45, timeout=10)

Changing CBP's mask; note that this can take up to a minute.

.. code::

    await cbp.cmd_changeMask.set_start(mask="1")

Getting telemetry from the CBP:

.. code::

    azimuth = await cbp.tel_azimuth.aget(timeout=2)
    altitude = await cbp.tel_altitude.aget(timeout=2)

Getting events from the CBP:

.. code::

    target = await cbp.evt_target.aget(timeout=2)
    in_position = await cbp.evt_inPosition.aget(timeout=2)

Clean up and shut down the script/notebook gracefully:

.. code::

    await domain.close()
