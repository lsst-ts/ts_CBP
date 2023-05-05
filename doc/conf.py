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
"""Sphinx configuration file for TSSW package"""

from documenteer.conf.pipelinespkg import *  # noqa

project = "ts_cbp"
html_theme_options["logotext"] = project  # noqa
html_title = project
html_short_title = project

intersphinx_mapping["ts_xml"] = ("https://ts-xml.lsst.io", None)  # noqa
intersphinx_mapping["ts_salobj"] = ("https://ts-salobj.lsst.io", None)  # noqa
intersphinx_mapping["ts_simactuators"] = (  # noqa
    "https://ts-simactuators.lsst.io",
    None,
)  # noqa
