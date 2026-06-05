"""
This module monitors general status like session status, services status, subscription status, etc.
"""

import blpapi
import logging

from .protocol import ModuleProtocol
from app.readiness import Readiness


# Configure logger for this module
logger = logging.getLogger(__name__)


# blpapi names
class SessionMsg:
    SLOW_CONSUMER_WARNING          = blpapi.Name("SlowConsumerWarning")
    SLOW_CONSUMER_WARNING_CLEARED  = blpapi.Name("SlowConsumerWarningCleared")

    SESSION_STARTED                = blpapi.Name("SessionStarted")
    SESSION_TERMINATED             = blpapi.Name("SessionTerminated")
    SESSION_STARTUP_FAILURE        = blpapi.Name("SessionStartupFailure")
    SESSION_CONNECTION_UP          = blpapi.Name("SessionConnectionUp")
    SESSION_CONNECTION_DOWN        = blpapi.Name("SessionConnectionDown")

    SERVICE_OPENED                 = blpapi.Name("ServiceOpened")
    SERVICE_OPEN_FAILURE           = blpapi.Name("ServiceOpenFailure")

    SUBSCRIPTION_FAILURE           = blpapi.Name("SubscriptionFailure")
    SUBSCRIPTION_STARTED           = blpapi.Name("SubscriptionStarted")
    SUBSCRIPTION_TERMINATED        = blpapi.Name("SubscriptionTerminated")
    SUBSCRIPTION_STREAMS_ACTIVATED = blpapi.Name("SubscriptionStreamsActivated")


class StatusMonitor(ModuleProtocol):
    """
    Logging module
    """
    def __init__(
            self,
            readiness: Readiness | None = None
    ):
        self.readiness = readiness


    def process_event(
            self,
            event  : blpapi.Event,
            session: blpapi.Session,
    ):
        match event.eventType():
            case blpapi.Event.SESSION_STATUS      : self.process_session_status_event(event, session)
            case blpapi.Event.SERVICE_STATUS      : self.process_service_status_event(event, session)
            case blpapi.Event.SUBSCRIPTION_STATUS : self.process_subscription_status_event(event, session)
            case blpapi.Event.ADMIN               : self.process_admin_event(event, session)
            case _: pass


    def process_session_status_event(self, event: blpapi.Event, session: blpapi.Session):
        for msg in event:
            match msg.messageType():
                case SessionMsg.SESSION_STARTED:
                    logger.info(f"Session started...")
                case SessionMsg.SESSION_STARTUP_FAILURE:
                    logger.error(f"Session startup failed")
                    if self.readiness: self.readiness.blpapi = False
                case SessionMsg.SESSION_CONNECTION_UP:
                    logger.info(f"Session connection is up")
                    if self.readiness: self.readiness.blpapi = True
                case SessionMsg.SESSION_CONNECTION_DOWN:
                    logger.info(f"Session connection is down")
                    if self.readiness: self.readiness.blpapi = False
                case SessionMsg.SESSION_TERMINATED:
                    logger.info(f"Session terminated")
                    if self.readiness: self.readiness.blpapi = False
                case _:
                    logger.info(f"{msg}")


    def process_service_status_event(self, event: blpapi.Event, session: blpapi.Session):
        for msg in event:
            match msg.messageType():
                case SessionMsg.SERVICE_OPENED       : logger.info(f"Service opened...")
                case SessionMsg.SERVICE_OPEN_FAILURE : logger.error(f"Service failed to open")
                case _: logger.info(f"{msg}")


    def process_subscription_status_event(self, event: blpapi.Event, session: blpapi.Session):
        for msg in event:
            match msg.messageType():
                case SessionMsg.SUBSCRIPTION_STARTED           : logger.info(f"Subscription started...")
                case SessionMsg.SUBSCRIPTION_FAILURE           : logger.error(f"Subscription failed to start: {msg}")
                case SessionMsg.SUBSCRIPTION_TERMINATED        : logger.error(f"Subscription terminated")
                case SessionMsg.SUBSCRIPTION_STREAMS_ACTIVATED : logger.info(f"Subscription streams activated")
                case _: logger.info(f"{msg}")


    def process_admin_event(self, event: blpapi.Event, session: blpapi.Session):
        for msg in event:
            match msg.messageType():
                case SessionMsg.SLOW_CONSUMER_WARNING         : logger.warning(f"SLOW CONSUMER WARNING")
                case SessionMsg.SLOW_CONSUMER_WARNING_CLEARED : logger.info(f"SLOW CONSUMER WARNING cleared")
                case _: logger.info(f"{msg}")