#
# This file is part of ts_cbp.
#
# Developed for the Rubin Observatory Telescope and Site System.
# This product includes software developed by the LSST Project
# (https://www.lsst.org).
# See the COPYRIGHT file at the top-level directory of this distribution
# for details of code ownership.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
import asyncio
import pathlib
import types
from typing import Any

from lsst.ts import salobj, utils

from . import __version__, component, mock_server
from .config_schema import CONFIG_SCHEMA
from .enums import ErrorCode

__all__ = ["CBPCSC", "execute_csc"]


TELEMETRY_INTERVAL = 1
IN_POSITION_TIMEOUT = 20
MASK_TIMEOUT = 90
POLLING_INTERVAL = 0.5


def execute_csc() -> None:
    """Run the CBP CSC command-line entry point."""
    asyncio.run(CBPCSC.amain(index=None))


class CBPCSC(salobj.ConfigurableCsc):
    """This defines the CBP CSC using ts_salobj.

    Parameters
    ----------
    simulation_mode : `int`, optional
        Supported simulation mode values

        * 0: normal operation
        * 1: mock controller
    initial_state : `lsst.ts.salobj.State`, optional
        Initial state is meant for unit tests, defaults to
        `lsst.ts.salobj.State.STANDBY`
    config_dir : `None` or `str` or `pathlib.Path`, optional
        Meant for unit tests.
        Tells the CSC where to look for the configuration files.
        Normal operation will always be in a configuration repository returned
        `get_config_dir`.

    Attributes
    ----------
    component : `CBPComponent`
        Component wrapper around the controller connection.
    simulator : `None` or `MockServer`
        Mock controller used in simulation mode.
    telemetry_task : `asyncio.Future`
        Background task that publishes telemetry.
    monitor_task : `asyncio.Future`
        Background task that reads hardware telemetry.
    telemetry_interval : `float`
        The interval that telemetry is published.
    in_position_timeout : `int`
        The time to wait for all encoders of the CBP to be in position.
    mask_timeout : `int`
        The time to wait for a mask motion to complete.
    in_position : `component.InPosition`
        Component-owned in-position snapshot used for command responses.
    polling_interval : `float`
        The interval between monitor reads.
    """

    valid_simulation_modes = (0, 1)
    """The valid simulation modes for the CBP."""
    version = __version__

    def __init__(
        self,
        simulation_mode: int = 0,
        initial_state: salobj.State = salobj.State.STANDBY,
        config_dir: pathlib.Path | str | None = None,
    ):
        super().__init__(
            name="CBP",
            index=0,
            config_dir=config_dir,
            initial_state=initial_state,
            simulation_mode=simulation_mode,
            config_schema=CONFIG_SCHEMA,
        )
        self.component: component.CBPComponent = component.CBPComponent(log=self.log)
        self.simulator: mock_server.MockServer | None = None
        self.telemetry_task: asyncio.Future[Any] = utils.make_done_future()
        self.monitor_task: asyncio.Future[Any] = utils.make_done_future()
        self.telemetry_interval = TELEMETRY_INTERVAL
        self.in_position_timeout = IN_POSITION_TIMEOUT
        self.mask_timeout = MASK_TIMEOUT  # 20 sec per mask.
        self.polling_interval = POLLING_INTERVAL
        self.log.info("CBP CSC initialized")

    @property
    def in_position(self) -> component.InPosition:
        """Return the component-owned command-facing in-position state."""
        return self.component.in_position

    @in_position.setter
    def in_position(self, in_position: component.InPosition) -> None:
        self.component.in_position = in_position

    def assert_unparked(self) -> None:
        """Assert that the CBP is not parked.

        Raises
        ------
        lsst.ts.salobj.ExpectedError
            Raised if the component telemetry reports that the CBP is parked.
        """
        if self.component.parked:
            raise salobj.ExpectedError("CBP still parked. Please call the unpark command.")

    async def publish_target(self, target: component.Target | None = None) -> None:
        """Publish a commanded target state."""
        if target is None:
            target = self.component.target

        await self.evt_target.set_write(
            azimuth=target.azimuth,
            elevation=target.elevation,
            focus=target.focus,
            mask=target.mask,
            mask_rotation=target.mask_rotation,
        )

    async def publish_in_position(self, in_position: component.InPosition | None = None) -> None:
        """Publish an in-position state.

        If ``in_position`` is provided, it is usually a telemetry-derived
        snapshot from `component.TelemetrySnapshot.in_position` or a
        command-facing snapshot from `component.TargetUpdate`. If omitted,
        this publishes the component-owned transient state.

        Parameters
        ----------
        in_position : `component.InPosition`, optional
            In-position snapshot to publish. If omitted, publish the
            component-owned transient in-position state.
        """
        if in_position is None:
            in_position = self.component.in_position

        await self.evt_inPosition.set_write(
            azimuth=in_position.azimuth,
            elevation=in_position.elevation,
            focus=in_position.focus,
            mask=in_position.mask,
            mask_rotation=in_position.mask_rotation,
        )

    async def publish_telemetry(self, telemetry: component.TelemetrySnapshot | None = None) -> None:
        """Publish component telemetry from one immutable snapshot.

        Parameters
        ----------
        telemetry : `component.TelemetrySnapshot`, optional
            Snapshot to publish. If omitted, the latest component snapshot is
            captured once at the start of the method.
        """
        if telemetry is None:
            telemetry = self.component.telemetry
        if not telemetry.valid:
            self.log.warning("Telemetry has not been updated by hardware.")
            return
        await self.tel_status.set_write(
            panic=telemetry.status.panic,
            azimuth=telemetry.status.azimuth,
            elevation=telemetry.status.elevation,
            mask=telemetry.status.mask,
            mask_rotation=telemetry.status.mask_rotation,
            focus=telemetry.status.focus,
        )
        await self.tel_parked.set_write(
            parked=telemetry.parked,
            autoparked=telemetry.autoparked,
        )
        await self.tel_azimuth.set_write(azimuth=telemetry.azimuth)
        await self.tel_elevation.set_write(elevation=telemetry.elevation)
        await self.tel_focus.set_write(focus=telemetry.focus)
        await self.tel_mask.set_write(
            mask=telemetry.mask,
            mask_rotation=telemetry.mask_rotation,
        )
        await self.publish_in_position(telemetry.in_position)

    async def do_move(self, data: salobj.BaseMsgType) -> None:
        """Move the CBP mount to a specified position.

        Parameters
        ----------
        data : `cmd_move.DataType`
            Command payload containing the target azimuth and elevation.

        """
        self.assert_enabled("move")
        self.assert_unparked()
        await self.publish_target_update(
            self.component.accept_target_update(
                azimuth=data.azimuth,
                elevation=data.elevation,
            )
        )
        await asyncio.gather(
            self.component.move_elevation(data.elevation),
            self.component.move_azimuth(data.azimuth),
        )
        await self.cmd_move.ack_in_progress(data, self.in_position_timeout)
        await asyncio.wait_for(self.wait_for_move_completion(), self.in_position_timeout)

    async def monitor(self) -> None:
        """Read hardware state and update component telemetry snapshots."""
        while True:
            if not self.component.connected and self.component.should_be_connected:
                reason = "Lost connection to controller."
                await self.component.notify_monitor_failure(reason)
                await self.fault(ErrorCode.CONNECTION_FAILED, report=reason)
                return
            try:
                telemetry = await self.component.update_status()
            except asyncio.CancelledError:
                await self.component.notify_monitor_failure("Monitor task cancelled.")
                raise
            except (ConnectionError, asyncio.IncompleteReadError):
                reason = "Lost connection to controller."
                await self.component.notify_monitor_failure(reason)
                await self.fault(ErrorCode.CONNECTION_FAILED, report=reason)
                return
            except component.CommandReplyError as e:
                reason = str(e)
                self.log.exception(reason)
                await self.component.notify_monitor_failure(reason)
                await self.fault(ErrorCode.REPLY_FAILED, report=reason)
                return
            except Exception:
                reason = "Monitor loop failed."
                self.log.exception(reason)
                await self.component.notify_monitor_failure(reason)
                await self.fault(
                    code=ErrorCode.MONITOR_LOOP_FAILED,
                    report=reason,
                )
                return
            if telemetry.status.panic:
                reason = "CBP panicked. Check hardware and reset device."
                await self.component.notify_monitor_failure(reason)
                await self.fault(
                    ErrorCode.PANICKED,
                    reason,
                )
                return
            await self.component.notify_monitor_success(telemetry)
            await asyncio.sleep(self.polling_interval)

    async def telemetry(self) -> None:
        """Publish the updated telemetry."""
        self.log.debug("Begin sending telemetry")
        while True:
            try:
                await self.publish_telemetry()
            except asyncio.CancelledError:
                raise
            except Exception:
                self.log.exception("Telemetry loop failed")
                await self.fault(
                    code=ErrorCode.TELEMETRY_LOOP_FAILED,
                    report="Telemetry loop failed.",
                )
                return
            await asyncio.sleep(self.telemetry_interval)

    async def do_setFocus(self, data: salobj.BaseMsgType) -> None:
        """Sets the focus.

        Parameters
        ----------
        data : `cmd_setFocus.DataType`
            Command payload containing the target focus value.
        """
        self.assert_enabled("setFocus")
        self.assert_unparked()
        await self.publish_target_update(self.component.accept_target_update(focus=data.focus))
        await self.component.change_focus(data.focus)
        await self.cmd_setFocus.ack_in_progress(data, self.in_position_timeout)
        await asyncio.wait_for(self.wait_for_move_completion(), self.in_position_timeout)

    async def do_park(self, data: salobj.BaseMsgType) -> None:
        """Park the CBP.

        Parameters
        ----------
        data : `cmd_park.DataType`
            Command payload for the park command.
        """
        self.assert_enabled("park")
        # TODO Check the reporting behavior for park
        await self.component.set_park()
        # await self.publish_telemetry()
        await self.cmd_park.ack_in_progress(data, timeout=self.in_position_timeout)
        await asyncio.wait_for(self.wait_for_park_completion(True), self.in_position_timeout)

    async def do_unpark(self, data: salobj.BaseMsgType) -> None:
        """Unpark the CBP.

        Parameters
        ----------
        data : `cmd_unpark.DataType`
            Command payload for the unpark command.
        """
        self.assert_enabled("unpark")
        await self.component.set_unpark()
        # Check the reporting behavior for unpark
        # await self.publish_telemetry()
        await self.cmd_unpark.ack_in_progress(data, self.in_position_timeout)
        await asyncio.wait_for(self.wait_for_park_completion(False), self.in_position_timeout)

    async def do_changeMask(self, data: salobj.BaseMsgType) -> None:
        """Changes the mask.

        Parameters
        ----------
        data : `cmd_changeMask.DataType`
            Command payload containing the target mask identifier.
        """
        self.assert_enabled("changeMask")
        self.assert_unparked()
        await self.publish_target_update(self.component.accept_mask_target_update(data.mask))
        await self.component.set_mask(data.mask)
        await self.cmd_changeMask.ack_in_progress(data, self.mask_timeout)
        await asyncio.wait_for(self.wait_for_move_completion(), self.mask_timeout)

    async def do_changeMaskRotation(self, data: salobj.BaseMsgType) -> None:
        """Changes the mask rotation variable and moves the
        current mask to that rotation value.

        Parameters
        ----------
        data : `cmd_changeMaskRotation.DataType`
            Command payload containing the target mask rotation.
        """
        self.assert_enabled("changeMaskRotation")
        self.assert_unparked()
        await self.publish_target_update(
            self.component.accept_target_update(mask_rotation=data.mask_rotation)
        )
        await self.component.set_mask_rotation(data.mask_rotation)
        await self.cmd_changeMaskRotation.ack_in_progress(data, self.mask_timeout)
        await asyncio.wait_for(self.wait_for_move_completion(), self.mask_timeout)

    async def handle_summary_state(self) -> None:
        """React to the current summary state and manage background tasks."""
        if self.disabled_or_enabled:
            if self.simulation_mode and self.simulator is None:
                self.simulator = mock_server.MockServer()
                await self.simulator.start_task
                self.component.host = self.simulator.host
                self.component.port = self.simulator.port
            if not self.component.connected:
                try:
                    await self.component.connect()
                except Exception:
                    self.log.exception("Failed to connect.")
                    await self.fault(ErrorCode.CONNECTION_FAILED, "Failed to connect.")
                    return
                # Get the status so that the target is updated
                # when transitioning from fault state so that
                # the inPosition event is set to True initially
                try:
                    telemetry = await self.component.update_status()
                except (ConnectionError, asyncio.IncompleteReadError):
                    await self.fault(ErrorCode.CONNECTION_FAILED, "Connection failed.")
                    return
                except Exception:
                    await self.fault(ErrorCode.TELEMETRY_LOOP_FAILED, "Failed to update status.")
                    return
                self.component.telemetry = telemetry
                self.component.initialize_target_from_telemetry()
                telemetry = self.component.telemetry
                await self.publish_target()
                await self.publish_telemetry(telemetry)
            if self.monitor_task.done():
                await self.component.clear_monitor_failure()
                self.monitor_task = asyncio.create_task(self.monitor())
            if self.telemetry_task.done():
                self.telemetry_task = asyncio.create_task(self.telemetry())
            if self.component.parked:
                await self.component.set_unpark()
                await asyncio.wait_for(self.wait_for_park_completion(False), self.in_position_timeout)
        else:
            await self.cancel_task(self.monitor_task)
            await self.cancel_task(self.telemetry_task)
            await self.component.disconnect()
            if self.simulator is not None:
                await self.simulator.close()
                self.simulator = None

    async def configure(self, config: types.SimpleNamespace) -> None:
        """Configure the CSC.

        Parameters
        ----------
        config : `types.SimpleNamespace`
            Parsed configuration namespace.
        """
        self.log.debug("We do configure indeed")
        self.component.configure(config)

    @staticmethod
    def get_config_pkg() -> str:
        """Return the name of the configuration repository.

        Returns
        -------
        config_pkg : `str`
            Name of the configuration package.
        """
        return "ts_config_mtcalsys"

    async def close_tasks(self) -> None:
        """Cancel CSC background tasks and close component resources."""
        await super().close_tasks()
        await self.cancel_task(self.monitor_task)
        await self.cancel_task(self.telemetry_task)
        await self.component.disconnect()
        if self.simulator is not None:
            await self.simulator.close()
            self.simulator = None

    async def wait_for_move_completion(self) -> None:
        """Wait for all axes of the CBP to be in position."""
        try:
            await self.component.wait_for_motion_complete(self.monitor_task)
        except component.MonitorStoppedError as e:
            raise salobj.ExpectedError(str(e)) from e
        self.log.info("Motion finished")

    async def cancel_task(self, task: asyncio.Future[Any]) -> None:
        """Cancel and await task result. noop if already done.

        Suppresses asyncio.CancelledError.

        Parameters
        ----------
        task : `asyncio.Future`
            The cancellable future or task to cancel and await.

        """
        if task.done():
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception:
            self.log.exception("Task failed while being cancelled.")

    async def wait_for_park_completion(self, parked: bool) -> None:
        """Wait for the monitor loop to observe the requested park state."""
        try:
            await self.component.wait_for_park_state(parked, self.monitor_task)
        except component.MonitorStoppedError as e:
            raise salobj.ExpectedError(str(e)) from e

    async def publish_target_update(self, target_update: component.TargetUpdate) -> None:
        """Publish an accepted component target update.

        Parameters
        ----------
        target_update : `component.TargetUpdate`
            Component-owned target update to publish through SAL.
        """
        await self.publish_target(target_update.target)
        await self.publish_in_position(target_update.in_position)
