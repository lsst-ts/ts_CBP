__all__ = ["CBPComponent"]

import asyncio
import logging
import types

from lsst.ts import tcpip


class CBPComponent:
    """This class is for implementing the CBP component.

    The component implements a python wrapper over :term:`DMC` code written by
    DFM Manufacturing.
    The following API exposes commands that move the motors of the CBP, sets
    the focus and selects the mask.

    Parameters
    ----------
    csc : `CBPCSC`
        The running CSC for the CBP.
    log : `None` or `logging.Logger`
        Optionally, the DDS logger can be passed to this class
        to publish log messages over DDS.

    Attributes
    ----------
    csc : `CBPCSC`
    log : `logging.Logger`
    reader : `asyncio.StreamReader` or `None`
    writer : `asyncio.StreamWriter` or `None`
    lock : `asyncio.Lock`
    timeout : `int`
    long_timeout : `int`
    host : `str`
    port : `int`
    connected : `bool`
    error_tolerance : `float`
    focus_crosstalk : `float`

    Notes
    -----

    The class uses the python socket module to build TCP/IP connections to the
    Galil controller for the CBP.
    The underlying API is built on :term:`DMC`.
    """

    def __init__(self, csc, log=None):
        self.csc = csc
        # Create a logger if none were passed during the instantiation of
        # the class
        if log is None:
            self.log = logging.getLogger(type(self).__name__)
        else:
            self.log = log.getChild(type(self).__name__)
        self.reader = None
        self.writer = None
        self.lock = asyncio.Lock()
        self.timeout = 5
        self.long_timeout = 30

        self.host = None
        self.port = None
        self.connected = False
        # According to the firmware, error limit is 9999 steps for watchdog
        # Conversion from steps to degrees is 186413 steps to one degree
        # 9999 divided by 186413 is approximately 0.053
        # So the value is set to 0.1
        self.error_tolerance = 0.1
        self.focus_crosstalk = 0.5
        self.terminator = "\r\n"
        self.generate_mask_info()
        self.log.info("CBP component initialized")

    @property
    def target(self):
        """Return target event data."""
        return self.csc.evt_target.data

    @property
    def in_position(self):
        """Return inPosition event data."""
        return self.csc.evt_inPosition.data

    @property
    def azimuth(self):
        """Return azimuth value."""
        return self.csc.tel_azimuth.data.azimuth

    @property
    def elevation(self):
        """Return elevation value."""
        return self.csc.tel_elevation.data.elevation

    @property
    def focus(self):
        """Return focus value."""
        return self.csc.tel_focus.data.focus

    @property
    def mask(self):
        """Return mask value."""
        return self.csc.tel_mask.data.mask

    @property
    def mask_rotation(self):
        """Return mask rotation value."""
        return self.csc.tel_mask.data.mask_rotation

    @property
    def parked(self):
        """Return parked value."""
        return self.csc.tel_parked.data.parked

    @property
    def auto_parked(self):
        """Return autoparked value."""
        return self.csc.tel_parked.data.autoparked

    @property
    def status(self):
        """Return status telemetry data."""
        return self.csc.tel_status.data

    def generate_mask_info(self):
        """Generate initial mask info."""
        mask_dict = {
            f"{i}": types.SimpleNamespace(name=f"Empty {i}", rotation=0, id=i)
            for i in (1, 2, 3, 4, 5, 9)
        }
        mask_dict["9"].name = "Unknown"
        self.masks = mask_dict

    async def update_in_position(self):
        """Update the in position status of each actuator,
        based on the most recently read encoder data.

        Returns
        --------
        did_change : `bool`
            True if anything changed (and so the event was published)
        """

        did_change = await self.csc.evt_inPosition.set_write(
            azimuth=abs(self.azimuth - self.target.azimuth) < self.error_tolerance,
            elevation=abs(self.elevation - self.target.elevation)
            < self.error_tolerance,
            mask=self.mask == self.target.mask,
            mask_rotation=(
                abs(self.mask_rotation - self.target.mask_rotation)
                < self.error_tolerance
            ),
            focus=abs(self.focus - self.target.focus) < self.focus_crosstalk,
        )
        return did_change

    async def send_command(
        self, msg, log=True, await_reply=True, await_terminator=True
    ):
        """Send the encoded command and read the reply.


        Parameters
        ----------
        msg : `str`
            The string command to be sent.
        log :  `bool`
            Call with False to suppress log messages.
            Useful for debugging purposes to limit output.
        await_reply : `bool`
            If false, don't wait for reply else wait for reply.
        await_terminator : `bool`
            If false, reply has no terminator else reply has expected
            terminator.

        Returns
        -------
        reply : `str`
            The reply to the command sent.
        """
        async with self.lock:
            msg = msg + self.terminator
            if log:
                self.log.info(f"Writing: {msg}")
            self.writer.write(msg.encode("ascii"))
            await self.writer.drain()

            if await_reply and await_terminator:
                reply = await asyncio.wait_for(
                    self.reader.readuntil(self.terminator.encode("ascii")), timeout=5
                )
            elif await_reply and not await_terminator:
                reply = await asyncio.wait_for(self.reader.read(1024), timeout=5)
            else:
                reply = ":"

            if reply != ":":
                if log:
                    self.log.debug(f"reply={reply}")
                reply = reply.decode("ascii").strip(f":{self.terminator}")
                if log:
                    self.log.debug(f"stripped reply={reply}")
            return reply

    async def connect(self):
        """Create a socket and connect to the CBP's static address and
        designated port.

        """
        async with self.lock:
            connect_task = asyncio.open_connection(host=self.host, port=self.port)
            self.reader, self.writer = await asyncio.wait_for(
                connect_task, timeout=self.long_timeout
            )
            self.connected = True

    async def disconnect(self):
        """Disconnect from the tcp socket.

        Safe to call even if already disconnected.
        """
        async with self.lock:
            if self.writer is None:
                return
            try:
                await tcpip.close_stream_writer(self.writer)
            except Exception:
                self.log.exception("disconnect failed, continuing")
            finally:
                self.writer = None
                self.reader = None
                self.connected = False

    async def get_azimuth(self):
        """Get the azimuth value."""
        azimuth = float(await self.send_command("az=?"))
        await self.csc.tel_azimuth.set_write(azimuth=azimuth)

    async def move_azimuth(self, position: float):
        """Move the azimuth encoder.

        Parameters
        ----------
        position : `float`
            The desired azimuth (degrees).

        Raises
        ------
        ValueError
            Raised when the new value falls outside the accepted range.

        """
        self.assert_in_range("azimuth", position, -45, 45)
        await self.csc.evt_inPosition.set_write(azimuth=False)
        await self.csc.evt_target.set_write(azimuth=position)
        await self.send_command(f"new_az={position}", await_terminator=False)

    async def get_elevation(self):
        """Read and record the mount elevation encoder, in degrees.

        Note that the low-level controller calls this axis "altitude".

        """
        elevation = float(await self.send_command("alt=?"))
        await self.csc.tel_elevation.set_write(elevation=elevation)

    async def move_elevation(self, position: float):
        """Move the elevation encoder.

        Parameters
        ----------
        position : `float`
            The desired elevation (degrees)

        Raises
        ------
        ValueError
            Raised when the new value falls outside the accepted range.

        """
        self.assert_in_range("elevation", position, -69, 45)
        await self.csc.evt_inPosition.set_write(elevation=False)
        await self.csc.evt_target.set_write(elevation=position)
        await self.send_command(f"new_alt={position}", await_terminator=False)
        self.log.debug("move_elevation command sent")

    async def get_focus(self):
        """Get the focus value."""
        focus = float(await self.send_command("foc=?"))
        await self.csc.tel_focus.set_write(focus=focus)

    async def change_focus(self, position: int):
        """Change focus.

        Parameters
        ----------
        position : `int`
            The value of the new focus (microns).

        Raises
        ------
        ValueError
            Raised when the new value falls outside the accepted range.
        """
        self.assert_in_range("focus", position, 0, 13000)
        await self.csc.evt_target.set_write(focus=int(position))
        self.log.debug("Sending new focus position")
        await self.send_command(f"new_foc={int(position)}", await_terminator=False)
        await self.csc.evt_inPosition.set_write(focus=False)
        self.log.debug("Change focus command sent)")

    async def get_mask(self):
        """Get mask and mask rotation value."""
        # If mask encoder is off then it will return "9.0" which is unknown
        # mask
        self.log.debug(f"{self.masks=}")
        mask = str(int(float(await self.send_command("msk=?"))))
        self.log.debug(f"{mask=}")
        mask = self.masks.get(mask).name
        mask_rotation = float(await self.send_command("rot=?", log=False))
        await self.csc.tel_mask.set_write(mask=mask, mask_rotation=mask_rotation)

    async def set_mask(self, mask: str):
        """Set the mask value

        Parameters
        ----------
        mask : `str`
            This is the name of the mask which is converted to an int using a
            dictionary.

        Raises
        ------
        KeyError
            Raised when new mask is not a key in the dictionary.

        """
        await self.csc.evt_target.set_write(mask=self.masks.get(mask).name)
        await self.send_command(
            f"new_msk={self.masks.get(mask).id}", await_terminator=False
        )

    async def set_mask_rotation(self, mask_rotation: float):
        """Set the mask rotation

        Parameters
        ----------
        mask_rotation : `float`
            The mask_rotation value that will be sent.


        Raises
        ------
        ValueError
            Raised when the new value falls outside the accepted range.

        """
        self.assert_in_range("mask_rotation", mask_rotation, 0, 360)
        await self.csc.evt_target.set_write(mask_rotation=mask_rotation)
        await self.send_command(f"new_rot={mask_rotation}", await_terminator=False)
        await self.csc.evt_inPosition.set_write(mask_rotation=False)

    async def check_park(self):
        """Get the park variable from CBP."""
        parked = bool(int(float(await self.send_command("park=?", log=False))))
        autoparked = bool(int(float(await self.send_command("autopark=?", log=False))))
        await self.csc.tel_parked.set_write(parked=parked, autoparked=autoparked)

    async def set_park(self):
        """Park the CBP."""
        await self.send_command("park=1", await_terminator=False)
        await self.check_park()

    async def set_unpark(self):
        """Unpark the CBP."""
        await self.send_command("park=0", await_terminator=False)
        await self.check_park()

    async def check_cbp_status(self):
        """Read and record the status of the encoders."""
        panic = bool(int(float(await self.send_command("wdpanic=?", log=False))))
        azimuth = bool(int(float(await self.send_command("AAstat=?", log=False))))
        elevation = bool(int(float(await self.send_command("ABstat=?", log=False))))
        mask = bool(int(float(await self.send_command("ACstat=?", log=False))))
        mask_rotation = bool(int(float(await self.send_command("ADstat=?", log=False))))
        focus = bool(int(float(await self.send_command("AEstat=?", log=False))))
        await self.csc.tel_status.set_write(
            panic=panic,
            azimuth=azimuth,
            elevation=elevation,
            mask=mask,
            mask_rotation=mask_rotation,
            focus=focus,
        )

    async def get_cbp_telemetry(self):
        """Get the position data of the CBP."""
        await self.get_elevation()
        await self.get_azimuth()
        await self.get_focus()
        await self.get_mask()

    def configure(self, config):
        """Configure the CBP.

        Parameters
        ----------
        config : `types.SimpleNamespace`
        """
        self.host = config.address
        self.port = config.port
        self.masks["1"].name = config.mask1["name"]
        self.masks["1"].rotation = config.mask1["rotation"]
        self.masks["2"].name = config.mask2["name"]
        self.masks["2"].rotation = config.mask2["rotation"]
        self.masks["3"].name = config.mask3["name"]
        self.masks["3"].rotation = config.mask3["rotation"]
        self.masks["4"].name = config.mask4["name"]
        self.masks["4"].rotation = config.mask4["rotation"]
        self.masks["5"].name = config.mask5["name"]
        self.masks["5"].rotation = config.mask5["rotation"]
        self.error_tolerance = config.encoder_tolerance
        self.focus_crosstalk = config.focus_crosstalk

    async def update_status(self):
        """Update the status."""
        await self.check_cbp_status()
        await self.check_park()
        await self.get_cbp_telemetry()
        await self.update_in_position()

    def assert_in_range(self, name, value, min_value, max_value):
        """Raise ValueError if a value is out of range.

        Parameters
        ----------
        name : `str`
            The name of the parameter.
        value : `float`
            The received value.
        min_value : `float`
            The minimum accepted value.
        max_value : `float`
            The maximum accepted value.

        Raises
        ------
        ValueError
            Raised when a value is outside of the given range.
        """
        if value < min_value or value > max_value:
            raise ValueError(
                f"{name} = {value} not in range [{min_value}, {max_value}]"
            )
