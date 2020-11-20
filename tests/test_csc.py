import asynctest
import unittest

from lsst.ts import salobj, cbp

STD_TIMEOUT = 15


class CBPCSCTestCase(asynctest.TestCase, salobj.BaseCscTestCase):
    def basic_make_csc(
        self, initial_state, config_dir=None, simulation_mode=1, **kwargs
    ):
        return cbp.csc.CBPCSC(
            initial_state=initial_state, simulation_mode=simulation_mode
        )

    async def test_standard_state_transitions(self):
        async with self.make_csc(initial_state=salobj.State.STANDBY, simulation_mode=1):
            await self.check_standard_state_transitions(
                enabled_commands=("changeMask", "move", "park", "unpark", "setFocus",)
            )

    async def test_bin_script(self):
        await self.check_bin_script(name="CBP", exe_name="run_cbp.py", index=None)

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
                azimuth=True,
                elevation=False,
                mask=True,
                mask_rotation=True,
                focus=True,
            )
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
                    azimuth=True,
                    elevation=False,
                    mask=True,
                    mask_rotation=True,
                    focus=True,
                )
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
                topic=self.remote.tel_mask, mask="Mask 1", mask_rotation=0
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
                mask="Mask 1",
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
            await self.remote.cmd_changeMask.set_start(mask="1", timeout=STD_TIMEOUT)
            await self.assert_next_sample(
                topic=self.remote.evt_target,
                azimuth=0,
                elevation=0,
                mask="Mask 1",
                mask_rotation=0,
                focus=0,
            )
            await self.assert_next_sample(
                topic=self.remote.tel_mask, mask="Mask 1", mask_rotation=0
            )

            with self.subTest("Not a mask"):
                with self.assertRaises(salobj.AckError):
                    await self.remote.cmd_changeMask.set_start(
                        mask="6", timeout=STD_TIMEOUT
                    )


if __name__ == "__main__":
    unittest.main()
