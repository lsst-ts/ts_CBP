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
import logging
import pathlib
import unittest
from typing import Any
from unittest import mock

from lsst.ts import cbp, salobj
from lsst.ts.cbp import component as cbp_component

STD_TIMEOUT = 15
LONG_TIMEOUT = 60
TEST_CONFIG_DIR = pathlib.Path(__file__).parents[1].joinpath("tests", "data", "config")


class CBPComponentTestCase(unittest.IsolatedAsyncioTestCase):
    class NoReplyClient:
        def __init__(self) -> None:
            self.writes: list[str] = []
            self.reply: bytes | None = None

        async def write_str(self, msg: str) -> None:
            self.writes.append(msg)

        async def read(self, n: int) -> bytes:
            if self.reply is not None:
                return self.reply
            await asyncio.Event().wait()
            raise AssertionError("unreachable")

    class ConnectionErrorClient:
        def __init__(self) -> None:
            self.writes: list[str] = []

        async def write_str(self, msg: str) -> None:
            self.writes.append(msg)

        async def read(self, n: int) -> bytes:
            raise ConnectionError("Lost connection.")

    async def test_send_command_lock_recovers_after_missing_reply(self) -> None:
        client = self.NoReplyClient()
        component = cbp_component.CBPComponent(
            log=logging.getLogger(type(self).__name__),
        )
        component.client = client

        with (
            mock.patch.object(cbp_component, "NUMBER_OF_RETRIES", 1),
            mock.patch.object(cbp_component, "TIMEOUT", 0.01),
            mock.patch.object(cbp_component.asyncio, "sleep", new=mock.AsyncMock()),
        ):
            with self.assertRaises(cbp_component.CommandReplyError):
                await component.send_command("no_reply", await_terminator=False)

            self.assertFalse(component.client_lock.locked())

            client.reply = b":"
            await asyncio.wait_for(
                component.send_command("reply", await_terminator=False),
                timeout=STD_TIMEOUT,
            )

        self.assertEqual(client.writes, ["no_reply", "reply"])

    async def test_send_command_reconnects_after_missing_reply(self) -> None:
        client = self.NoReplyClient()
        component = cbp_component.CBPComponent(
            log=logging.getLogger(type(self).__name__),
        )
        component.client = client
        component.host = "127.0.0.1"
        component.port = 12345
        component.disconnect = mock.AsyncMock()
        component.connect = mock.AsyncMock()

        with (
            mock.patch.object(cbp_component, "NUMBER_OF_RETRIES", 1),
            mock.patch.object(cbp_component, "TIMEOUT", 0.01),
            mock.patch.object(cbp_component.asyncio, "sleep", new=mock.AsyncMock()),
        ):
            with self.assertRaises(cbp_component.CommandReplyError) as cm:
                await component.send_command("no_reply", await_terminator=False)

        self.assertIn("connection reset", cm.exception.reason)
        component.disconnect.assert_awaited_once()
        component.connect.assert_awaited_once()
        self.assertFalse(component.client_lock.locked())
        self.assertEqual(client.writes, ["no_reply"])

    async def test_send_command_wraps_reconnect_failure(self) -> None:
        component = cbp_component.CBPComponent(
            log=logging.getLogger(type(self).__name__),
        )
        component.client = self.NoReplyClient()
        component.host = "127.0.0.1"
        component.port = 12345
        reconnect_error = ConnectionError("Reconnect failed.")
        component.disconnect = mock.AsyncMock()
        component.connect = mock.AsyncMock(side_effect=reconnect_error)

        with (
            mock.patch.object(cbp_component, "NUMBER_OF_RETRIES", 1),
            mock.patch.object(cbp_component, "TIMEOUT", 0.01),
            mock.patch.object(cbp_component.asyncio, "sleep", new=mock.AsyncMock()),
        ):
            with self.assertRaises(cbp_component.CommandReplyError) as cm:
                await component.send_command("no_reply", await_terminator=False)

        self.assertIn("reconnect failed", cm.exception.reason)
        self.assertIs(cm.exception.__cause__, reconnect_error)
        component.disconnect.assert_awaited_once()
        component.connect.assert_awaited_once()
        self.assertFalse(component.client_lock.locked())

    async def test_send_command_connection_error_releases_lock(self) -> None:
        component = cbp_component.CBPComponent(
            log=logging.getLogger(type(self).__name__),
        )
        component.client = self.ConnectionErrorClient()

        with self.assertRaises(ConnectionError):
            await component.send_command("connection_error", await_terminator=False)

        self.assertFalse(component.client_lock.locked())
        self.assertEqual(component.client.writes, ["connection_error"])


class CBPCSCTestCase(salobj.BaseCscTestCase, unittest.IsolatedAsyncioTestCase):
    def basic_make_csc(
        self,
        initial_state: salobj.State,
        config_dir: pathlib.Path | None = None,
        simulation_mode: int = 1,
        **kwargs: Any,
    ) -> cbp.csc.CBPCSC:
        return cbp.csc.CBPCSC(
            initial_state=initial_state,
            simulation_mode=simulation_mode,
            config_dir=TEST_CONFIG_DIR,
        )

    async def assert_in_position_state(self, timeout: float = STD_TIMEOUT, **kwargs: Any) -> Any:
        """Wait for evt_inPosition to match the requested field values."""
        async with asyncio.timeout(timeout):
            while True:
                data = await self.remote.evt_inPosition.next(flush=False, timeout=timeout)
                while data.private_sndStamp <= self.csc_start_time:
                    data = await self.remote.evt_inPosition.next(flush=False, timeout=timeout)
                for field_name in kwargs:
                    if not hasattr(data, field_name):
                        raise AssertionError(f"No such field {field_name} in evt_inPosition")
                if all(getattr(data, field_name) == expected for field_name, expected in kwargs.items()):
                    return data

    async def test_standard_state_transitions(self) -> None:
        async with self.make_csc(initial_state=salobj.State.STANDBY, simulation_mode=1):
            await self.check_standard_state_transitions(
                enabled_commands=(
                    "changeMask",
                    "changeMaskRotation",
                    "move",
                    "park",
                    "unpark",
                    "setFocus",
                )
            )

    async def test_bin_script(self) -> None:
        await self.check_bin_script(name="CBP", exe_name="run_cbp", index=None)

    async def test_move(self) -> None:
        async with self.make_csc(initial_state=salobj.State.ENABLED, simulation_mode=1):
            await self.assert_next_sample(
                topic=self.remote.evt_inPosition,
                azimuth=True,
                elevation=True,
                mask=True,
                mask_rotation=True,
                focus=True,
            )
            await self.remote.cmd_move.set_start(azimuth=-18.048, elevation=-17.890, timeout=STD_TIMEOUT)
            await self.assert_in_position_state(
                azimuth=False,
                elevation=False,
                mask=True,
                mask_rotation=True,
                focus=True,
            )
            await self.assert_in_position_state(
                azimuth=True,
                elevation=True,
                mask=True,
                mask_rotation=True,
                focus=True,
            )
            azimuth = await self.assert_next_sample(topic=self.remote.tel_azimuth, flush=True)
            elevation = await self.assert_next_sample(topic=self.remote.tel_elevation, flush=True)
            self.assertAlmostEqual(azimuth.azimuth, -18.048, delta=0.1)
            self.assertAlmostEqual(elevation.elevation, -17.890, delta=0.1)
            with self.subTest("Test move out of bounds."):
                with self.assertRaises(salobj.AckError):
                    await self.remote.cmd_move.set_start(azimuth=46, elevation=46)

            with self.subTest("Test move one axis out of bounds."):
                with self.assertRaises(salobj.AckError):
                    await self.remote.cmd_move.set_start(azimuth=46, elevation=30)

            with self.subTest("Test moving to the same position."):
                await self.remote.cmd_move.set_start(azimuth=20, elevation=-50)
                await self.assert_in_position_state(
                    azimuth=False,
                    elevation=False,
                    mask=True,
                    mask_rotation=True,
                    focus=True,
                )
                await self.assert_in_position_state(
                    azimuth=True,
                    elevation=True,
                    mask=True,
                    mask_rotation=True,
                    focus=True,
                )

    async def test_assert_unparked(self) -> None:
        async with self.make_csc(initial_state=salobj.State.ENABLED, simulation_mode=1):
            await self.remote.cmd_park.set_start()
            with self.assertRaises(salobj.AckError):
                await self.remote.cmd_move.set_start(azimuth=20, elevation=0)

    async def test_telemetry(self) -> None:
        async with self.make_csc(initial_state=salobj.State.ENABLED, simulation_mode=1):
            await self.assert_next_sample(
                topic=self.remote.tel_status,
                azimuth=False,
                elevation=False,
                panic=False,
                mask=False,
                mask_rotation=False,
                focus=False,
            )
            await self.assert_next_sample(topic=self.remote.tel_parked, autoparked=False, parked=False)
            await self.assert_next_sample(topic=self.remote.tel_azimuth, azimuth=0)
            await self.assert_next_sample(topic=self.remote.tel_elevation, elevation=0)
            await self.assert_next_sample(topic=self.remote.tel_focus, focus=0)
            await self.assert_next_sample(topic=self.remote.tel_mask, mask="mask 1", mask_rotation=0)
            await self.assert_next_sample(
                topic=self.remote.evt_inPosition,
                azimuth=True,
                elevation=True,
                mask=True,
                mask_rotation=True,
                focus=True,
            )
            await self.assert_next_sample(
                topic=self.remote.evt_target,
                azimuth=0,
                elevation=0,
                mask="mask 1",
                mask_rotation=0,
                focus=0,
                flush=False,
            )

    async def test_setFocus(self) -> None:
        async with self.make_csc(initial_state=salobj.State.ENABLED, simulation_mode=1):
            await self.assert_next_sample(
                topic=self.remote.evt_inPosition,
                azimuth=True,
                elevation=True,
                mask=True,
                mask_rotation=True,
                focus=True,
            )
            await self.remote.cmd_setFocus.set_start(focus=2500, timeout=STD_TIMEOUT)
            await self.assert_in_position_state(
                azimuth=True,
                elevation=True,
                mask=True,
                mask_rotation=True,
                focus=False,
            )
            await self.assert_in_position_state(
                azimuth=True,
                elevation=True,
                mask=True,
                mask_rotation=True,
                focus=True,
            )
            await self.assert_next_sample(topic=self.remote.tel_focus, flush=True, focus=2500)

            with self.subTest("Focus out of bounds"):
                with self.assertRaises(salobj.AckError):
                    await self.remote.cmd_setFocus.set_start(focus=14000, timeout=STD_TIMEOUT)

    async def test_park(self) -> None:
        async with self.make_csc(initial_state=salobj.State.ENABLED, simulation_mode=1):
            await self.remote.cmd_park.set_start(timeout=STD_TIMEOUT)
            await self.assert_next_sample(
                topic=self.remote.tel_parked, flush=True, parked=True, autoparked=False
            )

    async def test_unpark(self) -> None:
        async with self.make_csc(initial_state=salobj.State.ENABLED, simulation_mode=1):
            await self.remote.cmd_park.set_start(timeout=STD_TIMEOUT)
            await self.assert_next_sample(
                topic=self.remote.tel_parked, flush=True, parked=True, autoparked=False
            )
            await self.remote.cmd_unpark.set_start(timeout=STD_TIMEOUT)
            await self.assert_next_sample(
                topic=self.remote.tel_parked, flush=True, parked=False, autoparked=False
            )

    async def test_changeMask(self) -> None:
        async with self.make_csc(initial_state=salobj.State.ENABLED, simulation_mode=1):
            await self.assert_next_sample(
                topic=self.remote.evt_inPosition,
                azimuth=True,
                elevation=True,
                mask=True,
                mask_rotation=True,
                focus=True,
            )
            await self.remote.cmd_changeMask.set_start(mask="1", timeout=STD_TIMEOUT)
            await self.assert_in_position_state(
                azimuth=True,
                elevation=True,
                mask=False,
                mask_rotation=False,
                focus=True,
            )
            await self.assert_in_position_state(
                azimuth=True,
                elevation=True,
                mask=True,
                mask_rotation=True,
                focus=True,
            )

            await self.assert_next_sample(
                topic=self.remote.tel_mask,
                flush=True,
                mask="mask 1",
                mask_rotation=30.0,
            )

            with self.subTest("Not a mask"):
                with self.assertRaises(salobj.AckError):
                    await self.remote.cmd_changeMask.set_start(mask="6", timeout=STD_TIMEOUT)

    async def test_reconnect(self) -> None:
        async with self.make_csc(initial_state=salobj.State.ENABLED, simulation_mode=1):
            await self.remote.cmd_disable.set_start(timeout=STD_TIMEOUT)
            await self.remote.cmd_standby.set_start(timeout=STD_TIMEOUT)
            await self.remote.cmd_start.set_start(timeout=STD_TIMEOUT)
            await self.assert_next_sample(
                topic=self.remote.tel_status,
                azimuth=False,
                elevation=False,
                panic=False,
                mask=False,
                mask_rotation=False,
                focus=False,
            )

    async def test_fault(self) -> None:
        async with self.make_csc(initial_state=salobj.State.ENABLED, simulation_mode=1):
            await self.assert_next_summary_state(state=salobj.State.ENABLED)
            await self.csc.simulator.close()
            await self.assert_next_summary_state(state=salobj.State.FAULT, timeout=60)
            await self.assert_next_sample(self.remote.evt_errorCode)
            await self.assert_next_sample(
                self.remote.evt_errorCode,
                errorCode=cbp.enums.ErrorCode.CONNECTION_FAILED,
            )

    async def test_move_fails_if_monitor_fails_while_waiting(self) -> None:
        async with self.make_csc(initial_state=salobj.State.ENABLED, simulation_mode=1):
            await self.assert_next_sample(
                topic=self.remote.evt_inPosition,
                azimuth=True,
                elevation=True,
                mask=True,
                mask_rotation=True,
                focus=True,
            )

            self.csc.component.move_elevation = mock.AsyncMock()
            self.csc.component.move_azimuth = mock.AsyncMock()

            async def fail_monitor_after_command_starts() -> None:
                await asyncio.sleep(0)
                await self.csc.notify_monitor_failure("test monitor failure")

            fail_task = asyncio.create_task(fail_monitor_after_command_starts())

            with self.assertRaises(salobj.AckError) as cm:
                await self.remote.cmd_move.set_start(
                    azimuth=1,
                    elevation=1,
                    timeout=STD_TIMEOUT,
                )
            await fail_task
            self.assertIn("Monitor stopped while waiting for motion", cm.exception.ackcmd.result)

    async def test_move_times_out_if_target_never_reached(self) -> None:
        async with self.make_csc(initial_state=salobj.State.ENABLED, simulation_mode=1):
            self.csc.component.move_elevation = mock.AsyncMock()
            self.csc.component.move_azimuth = mock.AsyncMock()

            self.csc.in_position_timeout = 0.1
            self.csc.set_in_position(
                azimuth=False, elevation=False, focus=True, mask=True, mask_rotation=True
            )

            with self.assertRaises(salobj.AckError) as cm:
                await self.remote.cmd_move.set_start(
                    azimuth=1,
                    elevation=1,
                    timeout=STD_TIMEOUT,
                )

            self.assertEqual(cm.exception.ackcmd.result, "Timeout")


if __name__ == "__main__":
    unittest.main()
