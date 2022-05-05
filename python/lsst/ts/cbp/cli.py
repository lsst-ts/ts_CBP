__all__ = ["execute_csc"]

import asyncio

from . import CBPCSC


def execute_csc():
    asyncio.run(CBPCSC.amain(index=None))
