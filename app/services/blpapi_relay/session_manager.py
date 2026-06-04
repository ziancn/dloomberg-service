"""
This module houses the SessionManager class, which controls session lifecycle and event handling.
"""

import blpapi
import logging

from typing import List, Set

from .modules.protocol import ModuleProtocol


# Configure logger for this module
logger = logging.getLogger(__name__)


# Event name
EVENT_NAME = {
    blpapi.Event.UNKNOWN:              "UNKNOWN",
    blpapi.Event.ADMIN:                "ADMIN",
    blpapi.Event.SESSION_STATUS:       "SESSION_STATUS",
    blpapi.Event.SUBSCRIPTION_STATUS:  "SUBSCRIPTION_STATUS",
    blpapi.Event.REQUEST_STATUS:       "REQUEST_STATUS",
    blpapi.Event.RESPONSE:             "RESPONSE",
    blpapi.Event.PARTIAL_RESPONSE:     "PARTIAL_RESPONSE",
    blpapi.Event.SUBSCRIPTION_DATA:    "SUBSCRIPTION_DATA",
    blpapi.Event.SERVICE_STATUS:       "SERVICE_STATUS",
    blpapi.Event.TIMEOUT:              "TIMEOUT",
    blpapi.Event.AUTHORIZATION_STATUS: "AUTHORIZATION_STATUS",
    blpapi.Event.RESOLUTION_STATUS:    "RESOLUTION_STATUS",
    blpapi.Event.TOPIC_STATUS:         "TOPIC_STATUS",
    blpapi.Event.TOKEN_STATUS:         "TOKEN_STATUS",
    blpapi.Event.REQUEST:              "REQUEST",
}


class SessionManager:
    """
    SessionManager controls session connection, request/response handling and event distribution
    to registered modules which you can customize and extend.
    """
    def __init__(self, host: str = "localhost", port: int = 8194):
        session_options = blpapi.SessionOptions()
        session_options.setServerHost(host)
        session_options.setServerPort(port)

        self._session = blpapi.Session(session_options, self._process_event)
        self._modules: List[ModuleProtocol] = []
        self._opened_services: Set[str] = set()


    # PRIVATE
    def _process_event(self, event: blpapi.Event, session: blpapi.Session):
        et = event.eventType()
        logger.debug(f"{EVENT_NAME.get(et)} event received")
        # Broadcast event to all registered modules
        for module in self._modules:
            try:
               module.process_event(event, session)
            except Exception as e:
               logger.exception(f"Module '{module}' error: {e}")


    # PUBLIC
    @property
    def session(self) -> blpapi.Session:
        return self._session


    def start(self):
        if not self._session.start():
            raise RuntimeError("Failed to start EMSX session")


    def start_async(self):
        if not self._session.startAsync():
            raise RuntimeError("Failed to start(async) EMSX session")


    def stop(self):
        self._session.stop()


    def register_module(self, module: ModuleProtocol):
        if module not in self._modules:
            self._modules.append(module)
            if hasattr(module, "session"):
                logger.debug(f"Bind current session to module: {module}")
                module.session = self._session