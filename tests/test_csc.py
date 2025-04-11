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
import os
import pathlib
import unittest

from lsst.ts import cbp, salobj

STD_TIMEOUT = 15
TEST_CONFIG_DIR = pathlib.Path(__file__).parents[1].joinpath("tests", "data", "config")


class CBPCSCTestCase(salobj.BaseCscTestCase, unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        os.environ["LSST_SITE"] = "cbp"
        return super().setUp()

    def basic_make_csc(
        self, initial_state, config_dir=None, simulation_mode=1, **kwargs
    ):
        return cbp.csc.CBPCSC(
            initial_state=initial_state,
            simulation_mode=simulation_mode,
            config_dir=TEST_CONFIG_DIR,
        )

    async def test_standard_state_transitions(self):
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

    async def test_bin_script(self):
        await self.check_bin_script(name="CBP", exe_name="run_cbp", index=None)

    async def test_move(self):
        async with self.make_csc(initial_state=salobj.State.ENABLED, simulation_mode=1):
            await self.assert_next_sample(
                topic=self.remote.evt_inPosition,
                azimuth=True,
                elevation=True,
                mask=False,
                mask_rotation=True,
                focus=True,
            )
            await self.assert_next_sample(
                topic=self.remote.evt_inPosition,
                azimuth=True,
                elevation=True,
                mask=True,
                mask_rotation=True,
                focus=True,
            )
            await self.remote.cmd_move.set_start(
                azimuth=20, elevation=-50, timeout=STD_TIMEOUT
            )
            await self.assert_next_sample(
                topic=self.remote.evt_inPosition,
                azimuth=False,
                elevation=False,
                mask=True,
                mask_rotation=True,
                focus=True,
            )
            # await self.assert_next_sample(
            #     topic=self.remote.evt_inPosition,
            #     azimuth=False,
            #     elevation=False,
            #     mask=True,
            #     mask_rotation=True,
            #     focus=True,
            # )
            await self.assert_next_sample(
                topic=self.remote.evt_inPosition,
                azimuth=True,
                elevation=False,
                mask=True,
                mask_rotation=True,
                focus=True,
            )
            await self.assert_next_sample(
                topic=self.remote.evt_inPosition,
                azimuth=True,
                elevation=True,
                mask=True,
                mask_rotation=True,
                focus=True,
            )
            await self.assert_next_sample(
                topic=self.remote.tel_azimuth, flush=True, azimuth=20
            )
            await self.assert_next_sample(
                topic=self.remote.tel_elevation, flush=True, elevation=-50
            )
            with self.subTest("Test move out of bounds."):
                with self.assertRaises(salobj.AckError):
                    await self.remote.cmd_move.set_start(azimuth=46, elevation=46)

            with self.subTest("Test move one axis out of bounds."):
                with self.assertRaises(salobj.AckError):
                    await self.remote.cmd_move.set_start(azimuth=46, elevation=30)

            with self.subTest("Test moving to the same position."):
                await self.remote.cmd_move.set_start(azimuth=20, elevation=-50)
                await self.assert_next_sample(
                    topic=self.remote.evt_inPosition,
                    azimuth=False,
                    elevation=False,
                    mask=True,
                    mask_rotation=True,
                    focus=True,
                )
                await self.assert_next_sample(
                    topic=self.remote.evt_inPosition,
                    azimuth=True,
                    elevation=True,
                    mask=True,
                    mask_rotation=True,
                    focus=True,
                )

    async def test_assert_unparked(self):
        async with self.make_csc(initial_state=salobj.State.ENABLED, simulation_mode=1):
            await self.remote.cmd_park.set_start()
            with self.assertRaises(salobj.AckError):
                await self.remote.cmd_move.set_start(azimuth=20, elevation=0)

    async def test_telemetry(self):
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
            await self.assert_next_sample(
                topic=self.remote.tel_parked, autoparked=False, parked=False
            )
            await self.assert_next_sample(topic=self.remote.tel_azimuth, azimuth=0)
            await self.assert_next_sample(topic=self.remote.tel_elevation, elevation=0)
            await self.assert_next_sample(topic=self.remote.tel_focus, focus=0)
            await self.assert_next_sample(
                topic=self.remote.tel_mask, mask="mask 1", mask_rotation=0
            )
            await self.assert_next_sample(
                topic=self.remote.evt_inPosition,
                azimuth=True,
                elevation=True,
                mask=False,
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

    async def test_setFocus(self):
        async with self.make_csc(initial_state=salobj.State.ENABLED, simulation_mode=1):
            await self.assert_next_sample(
                topic=self.remote.evt_inPosition,
                azimuth=True,
                elevation=True,
                mask=False,
                mask_rotation=True,
                focus=True,
            )
            await self.assert_next_sample(
                topic=self.remote.evt_inPosition,
                azimuth=True,
                elevation=True,
                mask=True,
                mask_rotation=True,
                focus=True,
            )
            await self.remote.cmd_setFocus.set_start(focus=2500, timeout=STD_TIMEOUT)
            await self.assert_next_sample(
                topic=self.remote.evt_inPosition,
                azimuth=True,
                elevation=True,
                mask=True,
                mask_rotation=True,
                focus=False,
            )
            await self.assert_next_sample(
                topic=self.remote.evt_inPosition,
                azimuth=True,
                elevation=True,
                mask=True,
                mask_rotation=True,
                focus=True,
            )
            await self.assert_next_sample(
                topic=self.remote.tel_focus, flush=True, focus=2500
            )

            with self.subTest("Focus out of bounds"):
                with self.assertRaises(salobj.AckError):
                    await self.remote.cmd_setFocus.set_start(
                        focus=14000, timeout=STD_TIMEOUT
                    )

    async def test_park(self):
        async with self.make_csc(initial_state=salobj.State.ENABLED, simulation_mode=1):
            await self.remote.cmd_park.set_start(timeout=STD_TIMEOUT)
            await self.assert_next_sample(
                topic=self.remote.tel_parked, flush=True, parked=True, autoparked=False
            )

    async def test_unpark(self):
        async with self.make_csc(initial_state=salobj.State.ENABLED, simulation_mode=1):
            await self.remote.cmd_unpark.set_start(timeout=STD_TIMEOUT)
            await self.assert_next_sample(
                topic=self.remote.tel_parked, flush=True, parked=False, autoparked=False
            )

    async def test_changeMask(self):
        async with self.make_csc(initial_state=salobj.State.ENABLED, simulation_mode=1):
            await self.assert_next_sample(
                topic=self.remote.evt_inPosition,
                azimuth=True,
                elevation=True,
                mask=False,
                mask_rotation=True,
                focus=True,
            )
            await self.assert_next_sample(
                topic=self.remote.evt_inPosition,
                azimuth=True,
                elevation=True,
                mask=True,
                mask_rotation=True,
                focus=True,
            )
            await self.remote.cmd_changeMask.set_start(mask="1", timeout=STD_TIMEOUT)
            await self.assert_next_sample(
                topic=self.remote.evt_inPosition,
                azimuth=True,
                elevation=True,
                mask=False,
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
                    await self.remote.cmd_changeMask.set_start(
                        mask="6", timeout=STD_TIMEOUT
                    )

    async def test_reconnect(self):
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

    async def test_fault(self):
        async with self.make_csc(initial_state=salobj.State.ENABLED, simulation_mode=1):
            await self.assert_next_summary_state(state=salobj.State.ENABLED)
            await self.csc.simulator.close()
            await self.assert_next_summary_state(state=salobj.State.FAULT)


if __name__ == "__main__":
    unittest.main()
