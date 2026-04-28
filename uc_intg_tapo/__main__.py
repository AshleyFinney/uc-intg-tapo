"""Allow `python -m uc_intg_tapo` invocation."""

import asyncio

from uc_intg_tapo import main

if __name__ == "__main__":
    asyncio.run(main())
