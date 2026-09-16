# This file is part of ts_CBP.
#
# Developed for the Vera C. Rubin Observatory Telescope and Site Systems.
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
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""Public enumerations used by the CBP package."""

import enum


class ErrorCode(enum.IntEnum):
    """Error codes published by the CBP CSC.

    Attributes
    ----------
    CONNECTION_FAILED : `int`
        Connection to the controller failed or was lost.
    TELEMETRY_LOOP_FAILED : `int`
        Telemetry publishing failed.
    PANICKED : `int`
        The controller reported a panic condition.
    MONITOR_LOOP_FAILED : `int`
        Monitor loop failure while reading hardware telemetry.
    REPLY_FAILED : `int`
        Controller reply could not be parsed or was not received.
    """

    CONNECTION_FAILED = enum.auto()
    TELEMETRY_LOOP_FAILED = enum.auto()
    PANICKED = enum.auto()
    MONITOR_LOOP_FAILED = enum.auto()
    REPLY_FAILED = enum.auto()
