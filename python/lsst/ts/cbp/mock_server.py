__all__ = ["Encoders", "MockServer"]

import asyncio
import re
import logging
import enum

from lsst.ts import simactuators


class Encoders:
    """Mocks the CBP encoders.

    Attributes
    ----------
    AZIMUTH : `lsst.ts.simactuators.PointToPointActuator`
    ELEVATION : `lsst.ts.simactuators.PointToPointActuator`
    FOCUS : `lsst.ts.simactuators.PointToPointActuator`
    MASK_SELECT : `lsst.ts.simactuators.PointToPointActuator`
    MASK_ROTATE : `lsst.ts.simactuators.CircularPointToPointActuator`
    """

    def __init__(self):
        self.AZIMUTH = simactuators.PointToPointActuator(
            min_position=-45, max_position=45, speed=10, start_position=0
        )
        self.ELEVATION = simactuators.PointToPointActuator(
            min_position=-69, max_position=45, speed=10, start_position=0
        )
        self.FOCUS = simactuators.PointToPointActuator(
            min_position=0, max_position=13000, speed=200, start_position=0
        )
        self.MASK_SELECT = simactuators.PointToPointActuator(
            min_position=1, max_position=5, speed=1, start_position=1
        )
        self.MASK_ROTATE = simactuators.CircularPointToPointActuator(speed=10)


class StatusError(enum.Flag):
    NO = 0
    POSITION = 1
    SERIAL_ENCODER = enum.auto()
    SOFTWARE_LOWER_MOTION_LIMIT = enum.auto()
    SOFTWARE_UPPER_MOTION_LIMIT = enum.auto()
    HARDWARE_LOWER_MOTION_LIMIT = enum.auto()
    HARDWARE_UPPER_MOTION_LIMIT = enum.auto()
    TORQUE_LIMIT = enum.auto()


class MockServer:
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
        self.host = "127.0.0.1"
        self.port = 9999
        self.timeout = 5
        self.long_timeout = 30
        self.azimuth = 0
        self.altitude = 0
        self.focus = 0
        self.mask = 1
        self.panic_status = False
        self.encoders = Encoders()
        self.park = False
        self.auto_park = False
        self.masks_rotation = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
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
        self.log = logging.getLogger(__name__)

    async def start(self):
        """Start the server."""
        self.log.info("Starting Server")
        self.server = await asyncio.start_server(
            client_connected_cb=self.cmd_loop, host=self.host, port=self.port
        )

    async def stop(self):
        """Stop the server."""
        self.log.info("Closing Server")
        self.server.close()
        await asyncio.wait_for(self.server.wait_closed(), timeout=self.timeout)
        self.log.info("Server closed")

    async def cmd_loop(self, reader, writer):
        """Run the command loop.

        Parameters
        ----------
        reader : `asyncio.StreamReader`
        writer : `asyncio.StreamWriter`

        """
        while True:
            self.log.debug("In cmd loop")
            line = await reader.readuntil(b"\r")
            self.log.debug(f"Received: {line}")
            if not line:
                writer.close()
                return
            line = line.decode().strip("\r")
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
                        writer.write(msg.encode("ascii") + b"\r")
                        self.log.debug(f"Wrote {msg}")
                        await writer.drain()
                    break

    async def do_azimuth(self):
        """Return azimuth position.

        Returns
        -------
        str
        """
        return f"{self.encoders.AZIMUTH.position()}"

    async def do_new_azimuth(self, azimuth):
        """Set the new azimuth position.

        Parameters
        ----------
        azimuth : `float`

        Returns
        -------
        str
        """
        try:
            self.encoders.AZIMUTH.set_position(float(azimuth))
            return ""
        except ValueError:
            if float(azimuth) > 45:
                self.encoders.AZIMUTH.set_position(45)
                return ""
            elif float(azimuth) < -45:
                self.encoders.AZIMUTH.set_position(-45)
                return ""

    async def do_altitude(self):
        """Return the altitude position.

        Returns
        -------
        str
        """
        return f"{self.encoders.ELEVATION.position()}"

    async def do_new_altitude(self, altitude):
        """Set the new altitude position.

        Parameters
        ----------
        altitude : `float`

        Returns
        -------
        str
        """
        try:
            self.encoders.ELEVATION.set_position(float(altitude))
            return ""
        except ValueError:
            if float(altitude) > 45:
                self.encoders.ELEVATION.set_position(45)
                return ""
            elif float(altitude) < -69:
                self.encoders.ELEVATION.set_position(-69)
                return ""

    async def do_focus(self):
        """Return the focus value.

        Returns
        -------
        str
        """
        return f"{int(self.encoders.FOCUS.position())}"

    async def do_new_focus(self, focus):
        """Set the new focus value.

        Parameters
        ----------
        focus

        Returns
        -------
        str
        """
        try:
            self.encoders.FOCUS.set_position(int(focus))
            return ""
        except ValueError:
            if int(focus) > 13000:
                self.encoders.FOCUS.set_position(13000)
                return ""
            elif int(focus) < 0:
                self.encoders.FOCUS.set_position(0)
                return ""

    async def do_mask(self):
        """Return the mask value.

        Returns
        -------
        str
        """
        return f"{self.mask}"

    async def do_new_mask(self, mask):
        """Set the new mask value.

        Parameters
        ----------
        mask : `str`

        Returns
        -------
        str
        """
        try:
            self.mask = int(mask)
            return ""
        except ValueError:
            if mask > 5:
                self.mask = 5
                return ""
            elif mask < 1:
                self.mask = 1
                return ""

    async def do_rotation(self):
        """Return the mask rotation value.

        Returns
        -------
        str
        """
        return f"{self.masks_rotation[self.mask]}"

    async def do_new_rotation(self, rotation):
        """Set the new mask rotation value.

        Parameters
        ----------
        rotation : `float`

        Returns
        -------
        str
        """
        try:
            self.masks_rotation[self.mask] = float(rotation)
            return ""
        except ValueError:
            pass  # figure out what the real controller does

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
            return f"{int(self.park)}"
        else:
            self.log.info(f"Park: {park}")
            self.park = bool(int(park))
            self.log.info(f"Park: {self.park}")
            return ""

    async def do_panic(self):
        """Return the panic status value.

        Returns
        -------
        str
        """
        return f"{int(self.panic_status)}"

    async def do_aastat(self):
        """Return the azimuth encoder status.

        Returns
        -------
        str
        """
        return "0"

    async def do_abstat(self):
        """Return the altitude encoder status.

        Returns
        -------
        str
        """
        return "0"

    async def do_acstat(self):
        """Return the focus encoder status.

        Returns
        -------
        str
        """
        return "0"

    async def do_adstat(self):
        """Return the mask selection encoder status.

        Returns
        -------
        str
        """
        return "0"

    async def do_aestat(self):
        """Return the mask rotation encoder status.

        Returns
        -------
        str
        """
        return "0"

    async def do_autopark(self):
        """Return the autopark value.

        Returns
        -------
        str
        """
        return "0"
