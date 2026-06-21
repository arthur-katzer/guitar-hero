"""Compatibility import path for Sandbox audio detection.

The live detector is shared by Sandbox and Learn. This module remains so
existing Sandbox imports and tests do not depend on where that boundary lives.
"""

from interfaces.audio.pitch import *  # noqa: F401,F403
