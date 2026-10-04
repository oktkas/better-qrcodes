"""KiCad Action Plugin entry point for Better QR Codes."""

import os

try:
    import pcbnew  # noqa: F401
except ImportError:
    # Keep the model importable by normal Python for unit tests.
    pass
else:
    if os.environ.get("BETTER_QR_CODES_NO_REGISTER") != "1":
        from .plugin import BetterQrCodesPlugin

        BetterQrCodesPlugin().register()
