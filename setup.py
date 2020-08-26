import setuptools
import pathlib
import os
import sys

setup_reqs = ["setuptools_scm"]
install_reqs = []
test_reqs = [
    "pytest",
    "pytest-flake8",
    "pytest-coverage",
    "asynctest",
    "black",
]
dev_requires = install_reqs + test_reqs + ["documenteer[pipelines]"]
scm_version_template = """# Generated by setuptools_scm
__all__ = ["__version__"]
__version__ = "{version}"
"""
tools_path = pathlib.PurePosixPath(setuptools.__path__[0])
base_prefix = pathlib.PurePosixPath(sys.base_prefix)
data_files_path = tools_path.relative_to(base_prefix).parents[1]

setuptools.setup(
    name="ts-cbp",
    use_scm_version={
        "write_to": "python/lsst/ts/cbp/version.py",
        "write_to_template": scm_version_template,
    },
    setup_requires=setup_reqs,
    install_requires=install_reqs,
    extras_require={"dev": setup_reqs + install_reqs + test_reqs + dev_requires},
    packages=setuptools.find_namespace_packages(where="python"),
    package_dir={"": "python"},
    package_data={"": ["*.rst", "*.yaml"]},
    data_files=[(os.path.join(data_files_path, "schema"), ["schema/CBP.yaml"])],
    scripts=["bin/run_cbp.py", "bin/run_cbp_simulator.sh"],
    tests_require=test_reqs,
    license="GPL",
    project_urls={
        "Bug Tracker": "https://jira.lsstcorp.org/secure/Dashboard.jspa",
        "Source Code": "https://github.com/lsst-ts/ts_CBP",
    },
)
