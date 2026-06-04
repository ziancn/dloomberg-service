"""
EMSX modules protocol template
"""

import blpapi

from typing import Protocol


class ModuleProtocol(Protocol):
    def process_event(
            self,
            event  : blpapi.Event,
            session: blpapi.Session,
    ):
        ...