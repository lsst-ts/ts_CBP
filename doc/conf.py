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
