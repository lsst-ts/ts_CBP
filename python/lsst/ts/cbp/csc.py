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

from lsst.ts import salobj, utils

from . import __version__, component, mock_server
from .config_schema import CONFIG_SCHEMA
from .enums import ErrorCode

__all__ = ["CBPCSC", "execute_csc"]


def execute_csc():
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
    simulator : `None` or `MockServer`
    telemetry_task : `asyncio.Future`
    telemetry_interval : `float`
        The interval that telemetry is published.
    in_position_timeout : `int`
        The time to wait for all encoders of the CBP to be in position.
    """

    valid_simulation_modes = (0, 1)
    """The valid simulation modes for the CBP."""
    version = __version__

    def __init__(
        self,
        simulation_mode=0,
        initial_state: salobj.State = salobj.State.STANDBY,
        config_dir=None,
    ):
        super().__init__(
            name="CBP",
            index=0,
            config_dir=config_dir,
            initial_state=initial_state,
            simulation_mode=simulation_mode,
            config_schema=CONFIG_SCHEMA,
        )
        self.component = component.CBPComponent(self, log=self.log)
        self.simulator = None
        self.telemetry_task = utils.make_done_future()
        self.telemetry_interval = 0.5
        self.in_position_timeout = 20
        self.mask_timeout = 90  # 20 sec per mask.
        self.log.info("CBP CSC initialized")

    async def do_move(self, data):
        """Move the CBP mount to a specified position.

        Parameters
        ----------
        data : `cmd_move.DataType`

        """
        self.log.debug("Begin move")
        self.assert_enabled("move")
        await self.evt_inPosition.set_write(azimuth=False, elevation=False)
        await asyncio.gather(
            self.component.move_elevation(data.elevation),
            self.component.move_azimuth(data.azimuth),
        )

        self.log.debug("Waiting for in-position")
        await asyncio.wait_for(self.in_position(), self.in_position_timeout)

    async def telemetry(self):
        """Publish the updated telemetry."""
        while True:
            try:
                self.log.debug("Begin sending telemetry")
                await self.component.update_status()
                if self.component.status.panic:
                    await self.fault(
                        ErrorCode.PANICKED,
                        "CBP Panicked. Check hardware and reset device.",
                    )
                    return
            except asyncio.CancelledError:
                raise
            except Exception:
                self.log.exception("Telemetry loop failed")
                await self.fault(
                    code=ErrorCode.TELEMETRY_LOOP_FAILED,
                    report="Telemetry loop failed.",
                )
                return

            self.log.debug("Telemetry loop cycle completed")
            await asyncio.sleep(self.telemetry_interval)

    async def do_setFocus(self, data):
        """Sets the focus.

        Parameters
        ----------
        data : `cmd_setFocus.DataType`

        """
        self.assert_enabled("setFocus")
        await self.component.change_focus(data.focus)
        await asyncio.wait_for(self.in_position(), self.in_position_timeout)

    async def do_park(self, data):
        """Park the CBP.

        Parameters
        ----------
        data : `cmd_park.DataType`

        """
        self.assert_enabled("park")
        await self.component.set_park()
        await asyncio.wait_for(self.in_position(), self.in_position_timeout)

    async def do_unpark(self, data):
        """Unpark the CBP.

        Parameters
        ----------
        data : `cmd_unpark.DataType`
        """
        self.assert_enabled("unpark")
        await self.component.set_unpark()
        await asyncio.wait_for(self.in_position(), self.in_position_timeout)

    async def do_changeMask(self, data):
        """Changes the mask.

        Parameters
        ----------
        data : `cmd_changeMask.DataType`

        """
        self.assert_enabled("changeMask")
        await self.component.set_mask(str(data.mask))
        await asyncio.wait_for(self.in_position(), self.mask_timeout)

    async def do_changeMaskRotation(self, data):
        """Changes the mask rotation variable and moves the
        current mask to that rotation value.

        Parameters
        ----------
        data : `cmd_changeMaskRotation.DataType`

        """
        self.assert_enabled("changeMaskRotation")
        await self.component.set_mask_rotation(data.mask_rotation)
        await asyncio.wait_for(self.in_position(), self.mask_timeout)

    async def handle_summary_state(self):
        """Handle the summary state."""
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
                await self.component.update_status()
                await self.evt_target.set_write(
                    azimuth=self.component.azimuth,
                    elevation=self.component.elevation,
                    focus=self.component.focus,
                    mask=self.component.mask,
                    mask_rotation=self.component.mask_rotation,
                )
            if self.telemetry_task.done():
                self.telemetry_task = asyncio.create_task(self.telemetry())
            if self.component.parked:
                await self.component.set_unpark()
        else:
            self.telemetry_task.cancel()
            await self.component.disconnect()
            if self.simulator is not None:
                await self.simulator.close()
                self.simulator = None

    async def configure(self, config):
        """Configure the CSC.

        Parameters
        ----------
        config : `types.SimpleNamespace`
        """
        self.log.debug("We do configure indeed")
        self.component.configure(config)

    @staticmethod
    def get_config_pkg():
        """Return the name of the configuration repository."""
        return "ts_config_mtcalsys"

    async def close_tasks(self):
        await super().close_tasks()
        self.telemetry_task.cancel()
        await self.component.disconnect()
        if self.simulator is not None:
            await self.simulator.close()
            self.simulator = None

    async def in_position(self):
        """Wait for all axes of the CBP to be in position.

        In this case, in position is defined as the encoder values being
        within tolerance to the target values.
        """
        while not self.position:
            await asyncio.sleep(self.telemetry_interval)
        self.log.info("Motion finished")

    @property
    def position(self):
        """Is all of the axes of the CBP in position."""
        return (
            self.component.in_position.azimuth
            and self.component.in_position.elevation
            and self.component.in_position.focus
            and self.component.in_position.mask_rotation
            and self.component.in_position.mask
        )
