"""
This module handles //blp/bqlsvc requests and responses.
"""

import blpapi
import logging
import asyncio
import uuid

from .protocol import ModuleProtocol


# Configure logger for this module
logger = logging.getLogger(__name__)


def parse_bql_response(msg: blpapi.Message) -> dict:
    ...


class BqlHandler(ModuleProtocol):
    """
    This module handles //blp/bqlsvc requests and responses.
    """
    def __init__(self):
        self.session = None
        self._pending_requests = {}


    def process_event(
            self,
            event  : blpapi.Event,
            session: blpapi.Session,
    ):
        match event.eventType():
            case blpapi.Event.SESSION_STATUS   : self.process_session_status_event(event, session)
            case blpapi.Event.RESPONSE         : self.process_response(event, session)
            case blpapi.Event.PARTIAL_RESPONSE : self.process_response(event, session)
            case _: pass


    def process_session_status_event(self, event: blpapi.Event, session: blpapi.Session):
        for msg in event:
            if msg.messageType() == blpapi.Name("SessionStarted"):
                # If session is on, open service
                logger.info(f"Opening service: //blp/bqlsvc")
                session.openService("//blp/bqlsvc")


    def process_response(self, event: blpapi.Event, session: blpapi.Session):
        for msg in event:
            if not msg.correlationIds(): continue

            cid_value = msg.correlationIds()[0].value()
            logger.debug(f"Received response for CID: {cid_value}")
            print(str(msg))

            if cid_value in self._pending_requests:
                try:
                    # TODO: parse data into json
                    # data = parse_bql_response(msg)
                    data = str(msg)
                    loop = self._pending_requests[cid_value]["loop"]
                    future = self._pending_requests[cid_value]["future"]
                    if not future.done():
                        loop.call_soon_threadsafe(future.set_result, data)
                except Exception as e:
                    logger.exception(f"Error setting future result: {e}")
                    loop.call_soon_threadsafe(future.set_exception, e)
                finally:
                    if cid_value in self._pending_requests:
                        del self._pending_requests[cid_value]


    # Async APIs
    async def bquery(self, query: str) -> str:
        service = self.session.getService("//blp/bqlsvc")
        request = service.createRequest("sendQuery")

        request.set("expression", "query")

        cid = blpapi.CorrelationId(str(uuid.uuid4()))
        print(request)
        self.session.sendRequest(request, correlationId=cid)
        
        loop = asyncio.get_running_loop()
        future = loop.create_future()

        self._pending_requests[cid.value()] = {
            "future" : future,
            "loop"   : loop
        }

        try:
            result = await asyncio.wait_for(future, timeout=10.0)
            logger.debug(f"Response: {result}")
            return result
        except asyncio.TimeoutError:
            logger.error(f"Request timed out for CID: {cid.value()}")
            logger.debug(f"Request: {request.toString()}")
            raise
        finally:
            if cid.value() in self._pending_requests:
                del self._pending_requests[cid.value()]