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
__all__ = ["Encoders", "MockServer"]

import asyncio
import enum
import logging
import random
import re
from collections.abc import Awaitable, Callable

from lsst.ts import simactuators, tcpip


class Encoders:
    """Mocks the CBP encoders.

    Attributes
    ----------
    azimuth : `lsst.ts.simactuators.PointToPointActuator`
    elevation : `lsst.ts.simactuators.PointToPointActuator`
    focus : `lsst.ts.simactuators.PointToPointActuator`
    mask_select : `lsst.ts.simactuators.PointToPointActuator`
    mask_rotate : `lsst.ts.simactuators.CircularPointToPointActuator`
    """

    def __init__(self) -> None:
        self.azimuth = simactuators.PointToPointActuator(
            min_position=-45, max_position=45, speed=10, start_position=0
        )
        self.elevation = simactuators.PointToPointActuator(
            min_position=-69, max_position=45, speed=10, start_position=0
        )
        self.focus = simactuators.PointToPointActuator(
            min_position=0, max_position=13000, speed=1000, start_position=0
        )
        self.mask_select = simactuators.PointToPointActuator(
            min_position=1, max_position=5, speed=1, start_position=1
        )
        self.mask_rotate = simactuators.CircularPointToPointActuator(speed=10)


class StatusError(enum.Flag):
    """Status bits returned by the mock controller."""

    NO = 0
    POSITION = 1
    SERIAL_ENCODER = enum.auto()
    SOFTWARE_LOWER_MOTION_LIMIT = enum.auto()
    SOFTWARE_UPPER_MOTION_LIMIT = enum.auto()
    HARDWARE_LOWER_MOTION_LIMIT = enum.auto()
    HARDWARE_UPPER_MOTION_LIMIT = enum.auto()
    TORQUE_LIMIT = enum.auto()


class MockServer(tcpip.OneClientReadLoopServer):
    """Mocks the CBP server.

    Parameters
    ----------
    log : `logging.Logger`, optional
        Optional logger used for mock-server diagnostics.

    Attributes
    ----------
    host : `str`
    port : `int`
    timeout : `int`
    long_timeout : `int`
    azimuth : `float`
    altitude : `float`
    focus : `int`
    mask : `str`
    panic_status : `bool`
    encoders : `Encoders`
    park : `bool`
    auto_park : `bool`
    movement_reply : `str`
        Reply string returned by motion commands.
    commands : `tuple` of `re.Pattern` to `Callable`
        Command dispatch table.
    log : `logging.Logger`
    """

    def __init__(self, log: logging.Logger | None = None) -> None:
        self.log = logging.getLogger(__name__)
        self.timeout = 5
        self.long_timeout = 30
        self.azimuth = 0
        self.altitude = 0
        self.focus = 0
        self.mask = 1
        self.panic_status = 0.0
        self.encoders = Encoders()
        self.park = False
        self.auto_park = False
        self.movement_reply = ":"
        self.commands: tuple[tuple[re.Pattern[str], Callable[..., Awaitable[str | None]]], ...] = (
            (re.compile(r"az=\?"), self.do_azimuth),
            (re.compile(r"alt=\?"), self.do_altitude),
            (
                re.compile(r"new_alt=(?P<parameter>-?\d+(?:\.\d+)?)"),
                self.do_new_altitude,
            ),
            (re.compile(r"foc=\?"), self.do_focus),
            (
                re.compile(r"new_foc=(?P<parameter>0|[1-9]\d{0,3}|1[0-2]\d{3}|13000)"),
                self.do_new_focus,
            ),
            (re.compile(r"msk=\?"), self.do_mask),
            (re.compile(r"new_msk=(?P<parameter>[1-5])"), self.do_new_mask),
            (re.compile(r"rot=\?"), self.do_rotation),
            (
                re.compile(r"new_rot=(?P<parameter>-?\d+(?:\.\d+)?)"),
                self.do_new_rotation,
            ),
            (
                re.compile(r"new_az=(?P<parameter>-?\d+(?:\.\d+)?)"),
                self.do_new_azimuth,
            ),
            (re.compile(r"wdpanic=\?"), self.do_panic),
            (re.compile(r"autopark=\?"), self.do_autopark),
            (re.compile(r"park=(?P<parameter>[\?01])"), self.do_park),
            (re.compile(r"AAstat=\?"), self.do_aastat),
            (re.compile(r"ABstat=\?"), self.do_abstat),
            (re.compile(r"ACstat=\?"), self.do_acstat),
            (re.compile(r"ADstat=\?"), self.do_adstat),
            (re.compile(r"AEstat=\?"), self.do_aestat),
        )
        super().__init__(name="CBP Mock Server", host=tcpip.LOCAL_HOST, port=0, log=self.log)

    async def cmd_loop(self) -> None:
        """Run the command loop."""
        while self.connected:
            self.log.debug("In cmd loop")
            line = await self.reader.readuntil(self.terminator.encode())
            self.log.debug(f"Received: {line}")
            if not line:
                self.writer.close()
                return
            line = line.decode().strip(self.terminator)
            self.log.debug(f"Decoded {line}")
            for regex, command_method in self.commands:
                matched_command = regex.fullmatch(line)
                if matched_command:
                    self.log.debug(f"{line} match: {matched_command} method: {command_method}")
                    try:
                        parameter = matched_command.group("parameter")
                        self.log.debug(f"parameter={parameter}")
                    except IndexError:
                        parameter = None
                    try:
                        if parameter is None:
                            msg = await command_method()
                        else:
                            msg = await command_method(parameter)
                    except ValueError as e:
                        self.log.info(f"command {line} failed: {e}")
                        # TODO DM-27693: reply with an error signal so the
                        # client knows there is a problem
                    except Exception:
                        # An unexpected error; log a traceback
                        self.log.exception("Bug! Command {line} filed.")
                        # TODO DM-27693: reply with an error signal so the
                        # client knows there is a problem
                    else:
                        if msg is not None:
                            self.writer.write(msg.encode("ascii") + b"\r\n")
                            self.log.debug(f"Wrote {msg}")
                            await self.writer.drain()
                    break

    async def read_and_dispatch(self) -> None:
        """Read one command and dispatch it to the matching handler."""
        line = await self.read_str()
        for regex, command_method in self.commands:
            matched_command = regex.fullmatch(line)
            if matched_command:
                try:
                    parameter = matched_command.group("parameter")
                except IndexError:
                    parameter = None
                try:
                    if parameter is None:
                        msg = await command_method()
                    else:
                        msg = await command_method(parameter)
                except ValueError:
                    self.log.exception(f"Command {line} failed")
                except Exception:
                    self.log.exception(f"Command {line} failed unexpectedly")
                else:
                    if msg is not None:
                        bad_connection = True
                        while bad_connection:
                            bad_connection = random.choices([True, False], [0.3, 0.7])[0]
                            self.log.debug(f"{bad_connection=}")
                            if not bad_connection:
                                await self.write_str(msg)
                            await asyncio.sleep(0.2)
                break

    def set_constrained_position(self, value: float, actuator: simactuators.PointToPointActuator) -> None:
        """Set actuator to position that is silently constrained to bounds.

        Parameters
        ----------
        value : `float`
            Desired value
        actuator : `lsst.ts.simactuators.PointToPointActuator`
            The actuator to set.
        """
        constrained_value = min(max(value, actuator.min_position), actuator.max_position)
        self.log.info(f"constrained_value: {constrained_value}")
        actuator.set_position(constrained_value)

    def set_circular_constrained_position(
        self, value: float, actuator: simactuators.CircularPointToPointActuator
    ) -> None:
        """Set actuator to position that is silently constrained to bounds.

        Parameters
        ----------
        value : `float`
            Desired value
        actuator : `lsst.ts.simactuators.CircularPointToPointActuator`
            The actuator to set.
        """
        constrained_value = min(max(0, value), 360)
        self.log.info(f"constrained_value: {constrained_value}")
        self.log.debug(f"from actuator {actuator.set_position(constrained_value)}")
        actuator.set_position(constrained_value)

    async def do_azimuth(self) -> str:
        """Return azimuth position.

        Returns
        -------
        position : `str`
            Current azimuth position returned by the mock controller.
        """
        return f"{self.encoders.azimuth.position()}"

    async def do_new_azimuth(self, azimuth: str) -> str:
        """Set the new azimuth position.

        Parameters
        ----------
        azimuth : `str`
            Desired azimuth position in degrees.

        Returns
        -------
        reply : `str`
            Movement reply returned by the mock controller.
        """
        self.set_constrained_position(float(azimuth), self.encoders.azimuth)
        return self.movement_reply

    async def do_altitude(self) -> str:
        """Return the altitude position.

        Returns
        -------
        position : `str`
            Current altitude position returned by the mock controller.
        """
        return f"{self.encoders.elevation.position()}"

    async def do_new_altitude(self, altitude: str) -> str:
        """Set the new altitude position.

        Parameters
        ----------
        altitude : `str`
            Desired altitude position in degrees.

        Returns
        -------
        reply : `str`
            Movement reply returned by the mock controller.
        """
        self.set_constrained_position(float(altitude), self.encoders.elevation)
        return self.movement_reply

    async def do_focus(self) -> str:
        """Return the focus value.

        Returns
        -------
        position : `str`
            Current focus position returned by the mock controller.
        """
        return f"{int(self.encoders.focus.position())}"

    async def do_new_focus(self, focus: str) -> str:
        """Set the new focus value.

        Parameters
        ----------
        focus : `str`
            Desired focus position in microns.

        Returns
        -------
        reply : `str`
            Movement reply returned by the mock controller.
        """
        self.set_constrained_position(value=int(focus), actuator=self.encoders.focus)
        return self.movement_reply

    async def do_mask(self) -> str:
        """Return the mask value.

        Returns
        -------
        mask : `str`
            Current mask identifier returned by the mock controller.
        """
        self.log.debug(f"mask_select: {self.encoders.mask_select.position()}")
        return f"{self.encoders.mask_select.position()}"

    async def do_new_mask(self, mask: str) -> str:
        """Set the new mask value.

        Parameters
        ----------
        mask : `str`
            Desired mask identifier.

        Returns
        -------
        reply : `str`
            Movement reply returned by the mock controller.
        """
        self.set_constrained_position(value=int(mask), actuator=self.encoders.mask_select)
        return self.movement_reply

    async def do_rotation(self) -> str:
        """Return the mask rotation value.

        Returns
        -------
        rotation : `str`
            Current mask rotation returned by the mock controller.
        """
        self.log.debug(f"do_rotation {self.encoders.mask_rotate.position()}")
        return f"{self.encoders.mask_rotate.position()}"

    async def do_new_rotation(self, rotation: str) -> str:
        """Set the new mask rotation value.

        Parameters
        ----------
        rotation : `str`
            Desired mask rotation in degrees.

        Returns
        -------
        reply : `str`
            Movement reply returned by the mock controller.
        """
        self.log.debug(f"in mock server {rotation}")
        self.set_circular_constrained_position(value=float(rotation), actuator=self.encoders.mask_rotate)
        return self.movement_reply

    async def do_park(self, park: str = "?") -> str:
        """Park or unpark the CBP.

        Parameters
        ----------
        park : `str`, optional
            ``"?"`` queries the current park state, otherwise ``"0"`` or
            ``"1"`` sets it.

        Returns
        -------
        state : `str`
            Current or newly set park state returned by the mock controller.
        """
        if park == "?":
            self.log.info(f"Park: {self.park}")
            return f"{float(self.park)}"
        else:
            self.log.info(f"Park: {park}")
            self.park = bool(int(park))
            self.log.info(f"Park: {self.park}")
            return self.movement_reply

    async def do_panic(self) -> str:
        """Return the panic status value.

        Returns
        -------
        status : `str`
            Current panic status returned by the mock controller.
        """
        return f"{float(self.panic_status)}"

    async def do_aastat(self) -> str:
        """Return the azimuth encoder status.

        Returns
        -------
        status : `str`
            Current azimuth encoder status returned by the mock controller.
        """
        return f"{float(0)}"

    async def do_abstat(self) -> str:
        """Return the altitude encoder status.

        Returns
        -------
        status : `str`
            Current altitude encoder status returned by the mock controller.
        """
        return f"{float(0)}"

    async def do_acstat(self) -> str:
        """Return the focus encoder status.

        Returns
        -------
        status : `str`
            Current focus encoder status returned by the mock controller.
        """
        return f"{float(0)}"

    async def do_adstat(self) -> str:
        """Return the mask selection encoder status.

        Returns
        -------
        status : `str`
            Current mask selection encoder status returned by the mock
            controller.
        """
        return f"{float(0)}"

    async def do_aestat(self) -> str:
        """Return the mask rotation encoder status.

        Returns
        -------
        status : `str`
            Current mask rotation encoder status returned by the mock
            controller.
        """
        return f"{float(0)}"

    async def do_autopark(self) -> str:
        """Return the autopark value.

        Returns
        -------
        state : `str`
            Current autopark state returned by the mock controller.
        """
        return f"{float(0)}"
