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
import re

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

    def __init__(self):
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
    NO = 0
    POSITION = 1
    SERIAL_ENCODER = enum.auto()
    SOFTWARE_LOWER_MOTION_LIMIT = enum.auto()
    SOFTWARE_UPPER_MOTION_LIMIT = enum.auto()
    HARDWARE_LOWER_MOTION_LIMIT = enum.auto()
    HARDWARE_UPPER_MOTION_LIMIT = enum.auto()
    TORQUE_LIMIT = enum.auto()


class MockServer(tcpip.OneClientServer):
    """Mocks the CBP server.

    Parameters
    ----------
    log : `logging.Logger`, optional

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
    masks_rotation : `dict` of `str`:`float`
    commands : `tuple` of `re.Pattern`:`functools.partial`
    log : `logging.Logger`
    """

    def __init__(self, log=None):
        self.log = logging.getLogger(__name__)
        self.read_loop_task = asyncio.Future()
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
        self.masks_rotation = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        self.terminator = "\r\n"
        self.movement_reply = ":"
        self.commands = (
            (re.compile(r"az=\?"), self.do_azimuth),
            (re.compile(r"alt=\?"), self.do_altitude),
            (
                re.compile(r"new_alt=(?P<parameter>-?[0-6]\d?\.?\d?)"),
                self.do_new_altitude,
            ),
            (re.compile(r"foc=\?"), self.do_focus),
            (
                re.compile(r"new_foc=(?P<parameter>[0-1]?[0-3]?\d?\d?\d)"),
                self.do_new_focus,
            ),
            (re.compile(r"msk=\?"), self.do_mask),
            (re.compile(r"new_msk=(?P<parameter>[1-5])"), self.do_new_mask),
            (re.compile(r"rot=\?"), self.do_rotation),
            (
                re.compile(r"new_az=(?P<parameter>-?[0-3][0-5]?\.?\d?)"),
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
        super().__init__(
            name="CBP Mock Server",
            host=tcpip.LOCAL_HOST,
            port=9999,
            connect_callback=self.connect_callback,
            log=self.log,
        )

    async def connect_callback(self, server):
        self.read_loop_task.cancel()
        if server.connected:
            self.read_loop_task = asyncio.create_task(self.cmd_loop())

    async def cmd_loop(self):
        """Run the command loop.

        Parameters
        ----------
        reader : `asyncio.StreamReader`
        writer : `asyncio.StreamWriter`

        """
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
                    self.log.debug(
                        f"{line} match: {matched_command} method: {command_method}"
                    )
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

    def set_constrained_position(self, value, actuator):
        """Set actuator to position that is silently constrained to bounds.

        Parameters
        ----------
        value : `float`
            Desired value
        actuator : `lsst.ts.simactuators.PointToPointActuator`
            The actuator to set.
        """
        constrained_value = min(
            max(value, actuator.min_position), actuator.max_position
        )
        self.log.info(f"constrained_value: {constrained_value}")
        actuator.set_position(constrained_value)

    async def do_azimuth(self):
        """Return azimuth position.

        Returns
        -------
        str
        """
        return f"{self.encoders.azimuth.position()}"

    async def do_new_azimuth(self, azimuth):
        """Set the new azimuth position.

        Parameters
        ----------
        azimuth : `float`

        Returns
        -------
        str
        """
        self.set_constrained_position(float(azimuth), self.encoders.azimuth)
        return self.movement_reply

    async def do_altitude(self):
        """Return the altitude position.

        Returns
        -------
        str
        """
        return f"{self.encoders.elevation.position()}"

    async def do_new_altitude(self, altitude):
        """Set the new altitude position.

        Parameters
        ----------
        altitude : `float`

        Returns
        -------
        str
        """
        self.set_constrained_position(float(altitude), self.encoders.elevation)
        return self.movement_reply

    async def do_focus(self):
        """Return the focus value.

        Returns
        -------
        str
        """
        return f"{int(self.encoders.focus.position())}"

    async def do_new_focus(self, focus):
        """Set the new focus value.

        Parameters
        ----------
        focus

        Returns
        -------
        str
        """
        self.set_constrained_position(value=int(focus), actuator=self.encoders.focus)
        return self.movement_reply

    async def do_mask(self):
        """Return the mask value.

        Returns
        -------
        str
        """
        return f"{self.encoders.mask_select.position()}"

    async def do_new_mask(self, mask):
        """Set the new mask value.

        Parameters
        ----------
        mask : `str`

        Returns
        -------
        str
        """
        self.set_constrained_position(
            value=int(mask), actuator=self.encoders.mask_select
        )
        return self.movement_reply

    async def do_rotation(self):
        """Return the mask rotation value.

        Returns
        -------
        str
        """
        return f"{self.encoders.mask_rotate.position()}"

    async def do_new_rotation(self, rotation):
        """Set the new mask rotation value.

        Parameters
        ----------
        rotation : `float`

        Returns
        -------
        str
        """
        self.set_constrained_position(
            value=float(rotation), actuator=self.encoders.mask_rotate
        )
        return self.movement_reply

    async def do_park(self, park="?"):
        """Park or unpark the CBP.

        Parameters
        ----------
        park : `int`, optional

        Returns
        -------
        str
        """
        if park == "?":
            self.log.info(f"Park: {self.park}")
            return f"{float(self.park)}"
        else:
            self.log.info(f"Park: {park}")
            self.park = bool(int(park))
            self.log.info(f"Park: {self.park}")
            return self.movement_reply

    async def do_panic(self):
        """Return the panic status value.

        Returns
        -------
        str
        """
        return f"{float(self.panic_status)}"

    async def do_aastat(self):
        """Return the azimuth encoder status.

        Returns
        -------
        str
        """
        return f"{float(0)}"

    async def do_abstat(self):
        """Return the altitude encoder status.

        Returns
        -------
        str
        """
        return f"{float(0)}"

    async def do_acstat(self):
        """Return the focus encoder status.

        Returns
        -------
        str
        """
        return f"{float(0)}"

    async def do_adstat(self):
        """Return the mask selection encoder status.

        Returns
        -------
        str
        """
        return f"{float(0)}"

    async def do_aestat(self):
        """Return the mask rotation encoder status.

        Returns
        -------
        str
        """
        return f"{float(0)}"

    async def do_autopark(self):
        """Return the autopark value.

        Returns
        -------
        str
        """
        return f"{float(0)}"
