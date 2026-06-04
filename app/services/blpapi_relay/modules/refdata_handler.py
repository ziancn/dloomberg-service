"""
This module handles //blp/refdata requests and responses.
"""

import blpapi
import logging
import asyncio
import uuid

from .protocol import ModuleProtocol


# Configure logger for this module
logger = logging.getLogger(__name__)


def parse_refdata_response(msg: blpapi.Message) -> dict:
    # Utility method to parse Bloomberg response message into a more structured format
    data = {}

    if msg.hasElement("securityData"):
        sec_data_array = msg.getElement("securityData")
        for i in range(sec_data_array.numValues()):
            sec_data = sec_data_array.getValueAsElement(i)
            ticker = sec_data.getElementAsString("security")
            field_data = {}
            if sec_data.hasElement("fieldData"):
                fd = sec_data.getElement("fieldData")
                for j in range(fd.numElements()):
                    field = fd.getElement(j)
                    field_name = str(field.name())
                    field_value = field.getValue()
                    field_data[field_name] = field_value
            data[ticker] = field_data
    return data


class RefDataHandler(ModuleProtocol):
    """
    This module handles //blp/refdata requests and responses.
    """
    def __init__(self):
        self.session = None
        # Key: correlation_id, Value: {"future", "loop"}
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
                logger.info(f"Opening service: //blp/refdata")
                session.openService("//blp/refdata")


    def process_response(self, event: blpapi.Event, session: blpapi.Session):
        for msg in event:
            if not msg.correlationIds(): continue

            cid_value = msg.correlationIds()[0].value()
            logger.debug(f"Received response for CID: {cid_value}")

            if cid_value in self._pending_requests:
                try:
                    data = parse_refdata_response(msg)
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
    async def get_refdata(self, tickers: list[str], fields: list[str]) -> str:
        service = self.session.getService("//blp/refdata")
        request = service.createRequest("ReferenceDataRequest")

        for t in tickers:
            request.append("securities", t)
    
        for f in fields:
            request.append("fields", f)

        cid = blpapi.CorrelationId(str(uuid.uuid4()))
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