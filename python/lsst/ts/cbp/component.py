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
__all__ = [
    "CBPComponent",
    "Target",
    "TelemetrySnapshot",
    "InPosition",
    "Status",
    "CommandReplyError",
    "MaskTarget",
]

import asyncio
import contextlib
import dataclasses
import logging
import math
import types
from dataclasses import dataclass
from typing import Any, Literal, overload

from lsst.ts import tcpip

from .wizardry import NUMBER_OF_RETRIES

TIMEOUT = 1
NUMBER_OF_BYTES = 1024
MIN_AZIMUTH = -45
MAX_AZIMUTH = 45
MIN_ELEVATION = -69
MAX_ELEVATION = 45
MIN_FOCUS = 0
MAX_FOCUS = 13000
MIN_MASK_ROTATION = 0
MAX_MASK_ROTATION = 360


@dataclass(frozen=True)
class Target:
    """Commanded CBP target state.

    Attributes
    ----------
    azimuth : `float`
        Commanded azimuth angle in degrees.
    elevation : `float`
        Commanded elevation angle in degrees.
    focus : `float`
        Commanded focus position in microns.
    mask : `str`
        Commanded mask name.
    mask_rotation : `float`
        Commanded mask rotation in degrees.
    """

    azimuth: float
    elevation: float
    focus: float
    mask: str
    mask_rotation: float


@dataclass(frozen=True)
class InPosition:
    """Whether each CBP axis is at its target.

    Attributes
    ----------
    azimuth : `bool`
        True when azimuth is within tolerance of the target.
    elevation : `bool`
        True when elevation is within tolerance of the target.
    focus : `bool`
        True when focus is within tolerance of the target.
    mask : `bool`
        True when the mask matches the target.
    mask_rotation : `bool`
        True when mask rotation is within tolerance of the target.
    """

    azimuth: bool
    elevation: bool
    focus: bool
    mask: bool
    mask_rotation: bool


@dataclass(frozen=True)
class Status:
    """Hardware status bits reported by the CBP controller.

    Attributes
    ----------
    panic : `bool`
        True when the controller reports a panic condition.
    azimuth : `bool`
        Azimuth status bit from the controller.
    elevation : `bool`
        Elevation status bit from the controller.
    mask : `bool`
        Mask status bit from the controller.
    mask_rotation : `bool`
        Mask rotation status bit from the controller.
    focus : `bool`
        Focus status bit from the controller.
    """

    panic: bool
    azimuth: bool
    elevation: bool
    mask: bool
    mask_rotation: bool
    focus: bool


@dataclass(frozen=True)
class TelemetrySnapshot:
    """Immutable snapshot of hardware telemetry.

    Attributes
    ----------
    azimuth : `float`
        Measured azimuth angle in degrees.
    elevation : `float`
        Measured elevation angle in degrees.
    focus : `float`
        Measured focus position in microns.
    mask : `str`
        Measured mask name.
    mask_rotation : `float`
        Measured mask rotation in degrees.
    parked : `bool`
        True if the controller reports the mount is parked.
    autoparked : `bool`
        True if the controller reports the mount was automatically parked.
    status : `Status`
        Hardware status snapshot.
    in_position : `InPosition`
        In-position snapshot computed from the measured state.
    valid : `bool`
        True if the snapshot was populated from hardware. Initial values are
        placeholders and are intentionally marked invalid.
    """

    azimuth: float
    elevation: float
    focus: float
    mask: str
    mask_rotation: float
    parked: bool
    autoparked: bool
    status: Status
    in_position: InPosition
    valid: bool = False


@dataclass(frozen=True)
class MaskTarget:
    """Immutable mask target.

    Attributes
    ----------
    id : `int`
        Controller mask identifier.
    name : `str`
        Configured mask name.
    rotation : `float`
        Configured mask rotation in degrees.
    """

    id: int
    name: str
    rotation: float


class CommandReplyError(RuntimeError):
    """Raised when the controller does not return a usable command reply.

    Parameters
    ----------
    command : `str`
        Command that failed to produce a usable reply.
    reason : `str`
        Human-readable failure reason.

    Attributes
    ----------
    command : `str`
        Command that failed to produce a usable reply.
    reason : `str`
        Human-readable failure reason.
    """

    def __init__(self, command: str, reason: str) -> None:
        super().__init__(f"Command {command!r} failed: {reason}")
        self.command = command
        self.reason = reason


class CBPComponent:
    """This class is for implementing the CBP component.

    The component implements a python wrapper over :term:`DMC` code written by
    DFM Manufacturing.
    The following API exposes commands that move the motors of the CBP, sets
    the focus and selects the mask.

    Parameters
    ----------
    log : `None` or `logging.Logger`
        Optional logger used for component diagnostics.

    Attributes
    ----------
    log : `logging.Logger`
        Component logger.
    client : `lsst.ts.tcpip.Client`
        TCP client used to communicate with the controller.
    client_lock : `asyncio.Lock`
        Lock that serializes command traffic.
    timeout : `int`
        Short command timeout in seconds.
    long_timeout : `int`
        Long command timeout in seconds.
    host : `str`
        Controller host name or IP address.
    port : `int`
        Controller port.
    connected : `bool`
        True when the TCP client is connected.
    should_be_connected : `bool`
        True when the TCP client is expected to be connected.
    target : `Target`
        Latest commanded target snapshot.
    telemetry : `TelemetrySnapshot`
        Latest hardware telemetry snapshot.
    masks : `dict` of `str` to `types.SimpleNamespace`
        Configured mask metadata keyed by mask ID.
    error_tolerance : `float`
        Allowed azimuth/elevation error before the axis is considered out of
        position.
    rotation_tolerance : `float`
        Allowed mask rotation error before the axis is considered out of
        position.
    focus_crosstalk : `float`
        Allowed focus error before the axis is considered out of position.
    terminator : `str`
        Command terminator used by the controller protocol.

    Notes
    -----

    The class uses the python socket module to build TCP/IP connections to the
    Galil controller for the CBP.
    The underlying API is built on :term:`DMC`.
    """

    def __init__(self, log: logging.Logger | None = None):
        # Create a logger if none were passed during the instantiation of
        # the class
        if log is None:
            self.log = logging.getLogger(type(self).__name__)
        else:
            self.log = log.getChild(type(self).__name__)
        self.timeout = 5
        self.long_timeout = 30
        self.host: str | None = None
        self.port: int | None = None
        # According to the firmware, error limit is 9999 steps for watchdog
        # Conversion from steps to degrees is 186413 steps to one degree
        # 9999 divided by 186413 is approximately 0.053
        # So the value is set to 0.15 since there's some extra crosstalk
        self.error_tolerance = 0.15
        self.rotation_tolerance = 1e-5
        self.focus_crosstalk = 0.5
        self.client = tcpip.Client(host="", port=None, log=self.log)
        self.terminator = "\r\n"
        self.client_lock = asyncio.Lock()
        self.generate_mask_info()
        self.target = Target(
            azimuth=0,
            elevation=0,
            focus=0,
            mask="Unknown",
            mask_rotation=0,
        )
        self.telemetry = TelemetrySnapshot(
            azimuth=0,
            elevation=0,
            focus=0,
            mask="Unknown",
            mask_rotation=0,
            parked=False,
            autoparked=False,
            status=Status(False, False, False, False, False, False),
            in_position=InPosition(False, False, False, False, False),
        )
        self.log.info("CBP component initialized")

    @property
    def connected(self) -> bool:
        """Return whether the controller client is connected.

        Returns
        -------
        connected : `bool`
            True if the TCP/IP client is connected.
        """
        return self.client.connected

    @property
    def should_be_connected(self) -> bool:
        """Return whether the controller client should be connected.

        Returns
        -------
        should_be_connected : `bool`
            True if the TCP/IP client is expected to be connected.
        """
        return self.client.should_be_connected

    @property
    def azimuth(self) -> float:
        """Return the latest azimuth telemetry value.

        Returns
        -------
        azimuth : `float`
            Latest azimuth value from the component telemetry snapshot.
        """
        return self.telemetry.azimuth

    @property
    def elevation(self) -> float:
        """Return the latest elevation telemetry value.

        Returns
        -------
        elevation : `float`
            Latest elevation value from the component telemetry snapshot.
        """
        return self.telemetry.elevation

    @property
    def focus(self) -> float:
        """Return the latest focus telemetry value.

        Returns
        -------
        focus : `float`
            Latest focus value from the component telemetry snapshot.
        """
        return self.telemetry.focus

    @property
    def mask(self) -> str:
        """Return the latest mask telemetry value.

        Returns
        -------
        mask : `str`
            Latest mask name from the component telemetry snapshot.
        """
        return self.telemetry.mask

    @property
    def mask_rotation(self) -> float:
        """Return the latest mask rotation telemetry value.

        Returns
        -------
        mask_rotation : `float`
            Latest mask rotation value from the component telemetry snapshot.
        """
        return self.telemetry.mask_rotation

    @property
    def parked(self) -> bool:
        """Return the latest parked telemetry value.

        Returns
        -------
        parked : `bool`
            Latest parked state from the component telemetry snapshot.
        """
        return self.telemetry.parked

    @property
    def auto_parked(self) -> bool:
        """Return the latest autoparked telemetry value.

        Returns
        -------
        auto_parked : `bool`
            Latest autoparked state from the component telemetry snapshot.
        """
        return self.telemetry.autoparked

    def generate_mask_info(self) -> None:
        """Generate the initial mask metadata table.

        Notes
        -----
        The mask table is initialized with the controller IDs used by the
        mock server and configuration loader. `configure` later replaces the
        names and rotations with deployment-specific values.
        """
        mask_dict = {
            f"{i}": types.SimpleNamespace(name=f"Empty {i}", rotation=0, id=i) for i in (1, 2, 3, 4, 5, 9)
        }
        mask_dict["9"].name = "Unknown"
        self.masks: dict[str, types.SimpleNamespace] = mask_dict

    def set_target(self, **kwargs: Any) -> None:
        """Update the component target state.

        Parameters
        ----------
        **kwargs : `Any`
            Target fields and values to replace in the immutable target
            snapshot. Each key must name a field on `Target`.
        """
        self.validate_target(**kwargs)
        self.target = dataclasses.replace(self.target, **kwargs)

    async def _read_reply_with_retries(
        self, msg: str, command_name: str, kwargs: dict[str, Any], log: bool
    ) -> str | bytes | None:
        """Read a command reply, retrying short read timeouts.

        Parameters
        ----------
        msg : `str`
            Command string being read back from. Used for log messages.
        command_name : `str`
            Client read method name: ``"read_str"`` or ``"read"``.
        kwargs : `dict`
            Keyword arguments for the client read method.
        log : `bool`
            Log successful replies if true.

        Returns
        -------
        reply : `str`, `bytes`, or `None`
            The first non-empty reply, or None if no reply was received after
            all retry attempts.
        """
        reply = None

        for attempt in range(1, NUMBER_OF_RETRIES + 1):
            try:
                async with asyncio.timeout(TIMEOUT):
                    reply = await getattr(self.client, command_name)(**kwargs)
            except TimeoutError:
                self.log.warning(
                    "No reply for command %r on attempt %s/%s.",
                    msg,
                    attempt,
                    NUMBER_OF_RETRIES,
                )
                await asyncio.sleep(1)
                continue

            if reply:
                if log:
                    self.log.debug("Reply for %r: %r", msg, reply)
                return reply
        return None

    def _normalize_reply(self, msg: str, reply: str | bytes) -> str | bytes:
        """Strip controller prompt characters from a command reply.

        Parameters
        ----------
        msg : `str`
            Command string. Used only to report normalization errors.
        reply : `str` or `bytes`
            Raw controller reply.

        Returns
        -------
        reply : `str` or `bytes`
            Reply with leading and trailing colon prompt characters removed.

        Raises
        ------
        CommandReplyError
            Raised if the reply type is not supported.
        """
        if isinstance(reply, bytes):
            return reply.strip(b":")

        if isinstance(reply, str):
            return reply.strip(":")

        raise CommandReplyError(
            command=msg,
            reason=f"Unexpected reply type {type(reply).__name__}",
        )

    async def reconnect_after_reply_failure(self, msg: str) -> None:
        """Reconnect the controller socket after the reply stream stalls.

        This method is called while the command lock is held. That prevents
        another command from using the socket while it is being reset.

        Parameters
        ----------
        msg : `str`
            Command that did not receive a usable reply.
        """
        self.log.error(
            "No usable reply for command %r after %r attempts; reconnecting controller socket.",
            msg,
            NUMBER_OF_RETRIES,
        )

        with contextlib.suppress(Exception):
            await self.disconnect()
        if self.host is None or self.port is None:
            self.log.warning("Cannot reconnect controller socket because host/port are not configured")
            return

        await self.connect()

    @overload
    async def send_command(
        self,
        msg: str,
        log: bool = True,
        await_reply: Literal[True] = True,
        await_terminator: bool = True,
    ) -> str | bytes: ...

    @overload
    async def send_command(
        self,
        msg: str,
        log: bool = True,
        await_reply: Literal[False] = False,
        await_terminator: bool = True,
    ) -> None: ...

    async def send_command(
        self, msg: str, log: bool = True, await_reply: bool = True, await_terminator: bool = True
    ) -> str | bytes | None:
        """Send a controller command and optionally read its reply.

        Parameters
        ----------
        msg : `str`
            The string command to be sent.
        log : `bool`
            Call with False to suppress log messages.
            Useful for debugging purposes to limit output.
        await_reply : `bool`
            If false, do not wait for a reply.
        await_terminator : `bool`
            If false, read a fixed-size byte reply; otherwise read a
            terminator-delimited string reply.

        Returns
        -------
        reply : `str`, `bytes`, or `None`
            The normalized command reply, or None if ``await_reply`` is false.

        Raises
        ------
        CommandReplyError
            Raised if no usable reply is received after all retry attempts, if
            reconnecting after a missing reply fails, or if the reply type is
            unexpected.
        """
        command_name: str = "read_str" if await_terminator else "read"
        kwargs: dict[str, Any] = {} if await_terminator else {"n": NUMBER_OF_BYTES}
        async with self.client_lock:
            await self.client.write_str(msg)
            if not await_reply:
                return None

            reply = await self._read_reply_with_retries(
                msg=msg, command_name=command_name, kwargs=kwargs, log=log
            )
            if reply is None:
                try:
                    await self.reconnect_after_reply_failure(msg)
                except Exception as e:
                    raise CommandReplyError(
                        command=msg,
                        reason=(f"No reply after {NUMBER_OF_RETRIES} attempts; reconnect failed: {e!r}"),
                    ) from e
                raise CommandReplyError(
                    command=msg,
                    reason=(f"No reply after {NUMBER_OF_RETRIES} attempts; connection reset."),
                )

            return self._normalize_reply(msg, reply)

    async def connect(self) -> None:
        """Create a socket and connect to the CBP's static address and
        designated port.

        Raises
        ------
        Exception
            Raised when the controller connection cannot be established.

        """
        try:
            self.client = tcpip.Client(host=self.host, port=self.port, log=self.log)
            await self.client.start_task
        except Exception:
            self.log.exception("Connection failed.")
            raise

    async def disconnect(self) -> None:
        """Disconnect from the tcp socket.

        Safe to call even if already disconnected.
        """
        await self.client.close()
        self.client = tcpip.Client(host="", port=None, log=self.log)

    async def get_azimuth(self) -> float:
        """Read the current azimuth from hardware.

        Returns
        -------
        azimuth : `float`
            Current azimuth, in degrees.
        """
        return float(await self.send_command("az=?"))

    async def move_azimuth(self, position: float) -> None:
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
        self.assert_in_range("azimuth", position, MIN_AZIMUTH, MAX_AZIMUTH)
        self.set_target(azimuth=position)
        await self.send_command(f"new_az={position}", await_terminator=False)

    async def get_elevation(self) -> float:
        """Read and record the mount elevation encoder, in degrees.

        Note that the low-level controller calls this axis "altitude".

        Returns
        -------
        elevation : `float`
            Current elevation, in degrees.
        """
        return float(await self.send_command("alt=?"))

    async def move_elevation(self, position: float) -> None:
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
        self.assert_in_range("elevation", position, MIN_ELEVATION, MAX_ELEVATION)
        self.set_target(elevation=position)
        await self.send_command(f"new_alt={position}", await_terminator=False)
        self.log.debug("move_elevation command sent")

    async def get_focus(self) -> float:
        """Read the current focus from hardware.

        Returns
        -------
        focus : `float`
            Current focus, in microns.
        """
        return float(await self.send_command("foc=?"))

    async def change_focus(self, position: int) -> None:
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
        self.assert_in_range("focus", position, MIN_FOCUS, MAX_FOCUS)
        self.set_target(focus=int(position))
        self.log.debug("Sending new focus position")
        await self.send_command(f"new_foc={int(position)}", await_terminator=False)
        self.log.debug("Change focus command sent)")

    async def get_mask(self) -> tuple[str, float]:
        """Read the current mask name and mask rotation from hardware.

        Returns
        -------
        mask_name : `str`
            Current mask name.
        mask_rotation : `float`
            Current mask rotation, in degrees.
        """
        # If mask encoder is off then it will return "9.0" which is unknown
        # mask
        mask = str(int(float(await self.send_command("msk=?"))))
        mask_name = self.masks[mask].name
        mask_rotation = float(await self.send_command("rot=?", log=False))
        return mask_name, mask_rotation

    async def set_mask(self, mask: str) -> None:
        """Set the mask value

        Parameters
        ----------
        mask : `str`
            Mask identifier or key used to look up the configured mask.

        Raises
        ------
        KeyError
            Raised when new mask is not a key in the dictionary.

        """
        mask_target = self.get_mask_target(mask)
        self.set_target(mask=mask_target.name)
        await self.send_command(f"new_msk={mask_target.id}", await_terminator=False)
        await self.set_mask_rotation(mask_target.rotation)

    async def set_mask_rotation(self, mask_rotation: float) -> None:
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
        self.assert_in_range("mask_rotation", mask_rotation, MIN_MASK_ROTATION, MAX_MASK_ROTATION)
        self.set_target(mask_rotation=mask_rotation)

        self.log.debug(f"target: {self.target}")
        await self.send_command(f"new_rot={mask_rotation}", await_terminator=False)
        self.log.debug(f"Mask rotation command sent: {mask_rotation}")

    async def check_park(self) -> tuple[bool, bool]:
        """Read the current park and autopark states from hardware.

        Returns
        -------
        parked : `bool`
            True if the CBP is parked.
        auto_parked : `bool`
            True if the CBP is autoparked.
        """
        parked = bool(int(float(await self.send_command("park=?", log=False))))
        auto_parked = bool(int(float(await self.send_command("autopark=?", log=False))))
        return parked, auto_parked

    async def set_park(self) -> None:
        """Send the park command to the controller."""
        await self.send_command("park=1", await_terminator=False)

    async def set_unpark(self) -> None:
        """Send the unpark command to the controller."""
        await self.send_command("park=0", await_terminator=False)

    async def check_cbp_status(self) -> Status:
        """Read hardware status bits from the CBP controller.

        Returns
        -------
        status : `Status`
            Hardware status bits.
        """
        panic = bool(int(float(await self.send_command("wdpanic=?", log=False))))
        azimuth = bool(int(float(await self.send_command("AAstat=?", log=False))))
        elevation = bool(int(float(await self.send_command("ABstat=?", log=False))))
        mask = bool(int(float(await self.send_command("ACstat=?", log=False))))
        mask_rotation = bool(int(float(await self.send_command("ADstat=?", log=False))))
        focus = bool(int(float(await self.send_command("AEstat=?", log=False))))
        return Status(
            panic=panic,
            azimuth=azimuth,
            elevation=elevation,
            mask=mask,
            mask_rotation=mask_rotation,
            focus=focus,
        )

    def configure(self, config: types.SimpleNamespace) -> None:
        """Configure the CBP.

        Parameters
        ----------
        config : `types.SimpleNamespace`
            Configuration namespace produced by the CSC.
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

    async def update_status(self) -> TelemetrySnapshot:
        """Read hardware state and replace the telemetry snapshot.

        The new snapshot is built only after all telemetry fields have been
        read, so callers never observe a partially updated snapshot.

        Returns
        -------
        telemetry : `TelemetrySnapshot`
            Captured hardware snapshot.
        """
        status = await self.check_cbp_status()
        parked, autoparked = await self.check_park()
        elevation = await self.get_elevation()
        azimuth = await self.get_azimuth()
        focus = await self.get_focus()
        mask, mask_rotation = await self.get_mask()

        in_position = InPosition(
            azimuth=abs(azimuth - self.target.azimuth) < self.error_tolerance,
            elevation=abs(elevation - self.target.elevation) < self.error_tolerance,
            mask=mask == self.target.mask,
            mask_rotation=(
                1 - math.cos(math.radians(mask_rotation) - math.radians(self.target.mask_rotation))
                < self.rotation_tolerance
            ),
            focus=abs(focus - self.target.focus) < self.focus_crosstalk,
        )
        return TelemetrySnapshot(
            azimuth=azimuth,
            elevation=elevation,
            focus=focus,
            mask=mask,
            mask_rotation=mask_rotation,
            parked=parked,
            autoparked=autoparked,
            status=status,
            in_position=in_position,
            valid=True,
        )

    def assert_in_range(self, name: str, value: float, min_value: float, max_value: float) -> None:
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
            raise ValueError(f"{name} = {value} not in range [{min_value}, {max_value}]")

    def initialize_target_from_telemetry(self) -> None:
        """Initialize target from the latest hardware telemetry.

        This is used during startup so that the CSC's initial target matches
        the current hardware position. Because the target is set equal to the
        measured state, the resulting telemetry snapshot reports all axes in
        position.

        Raises
        ------
        RuntimeError
            Raised if no valid hardware telemetry has been read.
        """
        telemetry = self.telemetry
        if not telemetry.valid:
            raise RuntimeError("Cannot initialize target without data from hardware.")

        self.set_target(
            azimuth=telemetry.azimuth,
            elevation=telemetry.elevation,
            focus=telemetry.focus,
            mask=telemetry.mask,
            mask_rotation=telemetry.mask_rotation,
        )

        self.telemetry = dataclasses.replace(
            telemetry,
            in_position=InPosition(
                azimuth=True,
                elevation=True,
                focus=True,
                mask=True,
                mask_rotation=True,
            ),
        )

    def validate_target(
        self,
        azimuth: float | None = None,
        elevation: float | None = None,
        focus: float | None = None,
        mask: str | None = None,
        mask_rotation: float | None = None,
    ) -> None:
        """Validate target fields before mutating component state.

        Parameters
        ----------
        azimuth : `float`, optional
            Proposed azimuth target.
        elevation : `float`, optional
            Proposed elevation target.
        focus : `float`, optional
            Proposed focus target.
        mask : `str`, optional
            Proposed mask name.
        mask_rotation : `float`, optional
            Proposed mask rotation target.

        Raises
        ------
        ValueError
            Raised if any provided target value is out of range or not one of
            the configured masks.
        """
        if azimuth is not None:
            self.assert_in_range("azimuth", azimuth, MIN_AZIMUTH, MAX_AZIMUTH)
        if elevation is not None:
            self.assert_in_range("elevation", elevation, MIN_ELEVATION, MAX_ELEVATION)
        if focus is not None:
            self.assert_in_range("focus", focus, MIN_FOCUS, MAX_FOCUS)
        if mask is not None:
            allowed_names = {info.name for info in self.masks.values()}
            if mask not in allowed_names:
                raise ValueError(f"{mask} is not a configured mask name.")
        if mask_rotation is not None:
            self.assert_in_range("mask_rotation", mask_rotation, MIN_MASK_ROTATION, MAX_MASK_ROTATION)

    def get_mask_target(self, mask: str | int) -> MaskTarget:
        """Resolve a configured mask into a normalized target record.

        Parameters
        ----------
        mask : `str` or `int`
            Mask identifier accepted by the controller and configuration.

        Returns
        -------
        mask_target : `MaskTarget`
            Normalized mask target data.
        """
        mask_id = str(mask)
        if mask_id not in self.masks:
            raise ValueError(f"{mask_id} not in list of allowed masks.")
        mask_info = self.masks[mask_id]
        return MaskTarget(id=mask_info.id, name=mask_info.name, rotation=float(mask_info.rotation))
