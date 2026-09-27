import asyncio

import pytest


@pytest.fixture(autouse=True)
def _ensure_event_loop():
    # asyncio.run() di tes lain menutup & melepas loop; tes lama memakai get_event_loop().
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())
    yield
