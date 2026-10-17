"""CRVX TurboFrame - FPS Boost Engine for Minecraft Bedrock/PE (Android).

Zero-dependency (stdlib only). Python 3.9+.
"""

from __future__ import annotations

__version__ = "2026.10.1"
__codename__ = "TURBOFRAME / Absolute"
__engine_revision__ = "r7"

MC_PACKAGE_CANDIDATES = (
    "com.mojang.minecraftpe",
    "com.mojang.minecraftpe.beta",
    "com.mojang.minecraftpe.preview",
)

__all__ = ["__version__", "__codename__", "__engine_revision__", "MC_PACKAGE_CANDIDATES"]
