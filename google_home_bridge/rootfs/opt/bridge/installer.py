"""Install the bundled custom integration into the HA config directory."""

from __future__ import annotations

import filecmp
import logging
import os
import shutil

from options import COMPONENT_DST, COMPONENT_SRC

_LOGGER = logging.getLogger(__name__)


def integration_installed() -> bool:
    """Return if the shim integration is present in the config directory."""
    return os.path.isfile(os.path.join(COMPONENT_DST, "manifest.json"))


def integration_up_to_date() -> bool:
    """Return if the installed integration matches the bundled one."""
    if not integration_installed():
        return False
    comparison = filecmp.dircmp(COMPONENT_SRC, COMPONENT_DST)
    return not (
        comparison.left_only
        or comparison.right_only
        or comparison.diff_files
        or comparison.funny_files
    )


def install_integration() -> bool:
    """Copy the bundled integration into place. Returns True if changed."""
    if integration_up_to_date():
        return False
    os.makedirs(os.path.dirname(COMPONENT_DST), exist_ok=True)
    if os.path.isdir(COMPONENT_DST):
        shutil.rmtree(COMPONENT_DST)
    shutil.copytree(COMPONENT_SRC, COMPONENT_DST)
    _LOGGER.info("Installed cloud shim integration to %s", COMPONENT_DST)
    return True
