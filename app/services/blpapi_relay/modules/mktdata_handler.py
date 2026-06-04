"""
This module handles subscription requests and responses for real-time data from Bloomberg API
and manages connections with frontend clients via WebSockets.

STRUCTURE OF SUBSCRIPTION STRING

 "//blp/mktdata/ticker/IBM US Equity?fields=BID,ASK&interval=2"
  |-----------||------||-----------||------------------------|
        |          |         |                  |
     Service    Prefix   Instrument           Suffix

"""

import blpapi
import logging
import asyncio
import json
import datetime

from fastapi import WebSocket

from .protocol import ModuleProtocol


logger = logging.getLogger(__name__)


# Utility parse method
def parse_mktdata_event_msg(msg):
    cid = msg.correlationIds()[0].value()
    
    msg_dict = {
        "MESSAGE_TYPE": str(msg.messageType()),
        "CORRELATION_ID": str(cid),
        "TOPIC": str(msg.topicName())
    }

    # (Element)
    for i in range(msg.numElements()):
        element = msg.getElement(i)
        name = str(element.name())
        
        # 1. Python: None (JSON: null)
        if element.isNull():
            msg_dict[name] = None
            continue
            
        # 2. This is also AI generated, I am not very clear with BLPAPI DataTypes
        if element.datatype() in [blpapi.DataType.CHOICE, blpapi.DataType.SEQUENCE]:
            try:
                msg_dict[name] = str(element.getValue())
            except:
                pass
            continue

        value = element.getValue()
        
        # 3. Cross Platform datatype alignment
        if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
            msg_dict[name] = value.isoformat()
        elif isinstance(value, blpapi.Name):
            msg_dict[name] = str(value)
        elif isinstance(value, (int, float, bool, str)):
            msg_dict[name] = value
        else:
            msg_dict[name] = str(value)  # stringfy unknown types
            
    return msg_dict



class MktDataHandler(ModuleProtocol):
    def __init__(self, loop = None):
        self.session: blpapi.Session = None
        self.loop = loop or asyncio.get_event_loop()

        self.ticker_to_websockets: dict[str, set[WebSocket]] = {}
        self.ticker_to_fields: dict[str, set[str]] = {}

    
    def process_event(
            self,
            event  : blpapi.Event,
            session: blpapi.Session,
    ):
        match event.eventType():
            case blpapi.Event.SESSION_STATUS    : self.process_session_status_event(event, session)
            case blpapi.Event.SUBSCRIPTION_DATA : self.process_subscription_data(event, session)
            case _: pass


    def process_session_status_event(self, event: blpapi.Event, session: blpapi.Session):
        for msg in event:
            if msg.messageType() == blpapi.Name("SessionStarted"):
                # If session is on, open service
                logger.info(f"Opening service: //blp/mktdata")
                session.openService("//blp/mktdata")


    def process_subscription_data(self, event: blpapi.Event, session: blpapi.Session):
        for msg in event:
            if not msg.correlationIds(): continue

            ticker = msg.correlationIds()[0].value()

            if ticker in self.ticker_to_fields:
                logger.debug(f"Processing subscription data for {ticker}")
                data = parse_mktdata_event_msg(msg)
                self.broadcast(ticker, data)


    # ====================
    # WebSocket management 
    # ====================

    def broadcast(self, ticker: str, data: dict):
        if self.loop.is_running():
            asyncio.run_coroutine_threadsafe(self.send_update(ticker, data), self.loop)
        else:
            logger.warning("Asyncio event loop is not running. Cannot broadcast update.")


    async def send_update(self, ticker: str, data: dict):
        """Send update to all WebSockets that subscribed to a ticker"""
        json_payload = json.dumps(data)
        logger.debug(f"Broadcasting data for subscribers of {ticker}")
        if ticker in self.ticker_to_websockets:
            sockets = self.ticker_to_websockets[ticker]
            if sockets:
                await asyncio.gather(
                    *[ws.send_json(json_payload) for ws in sockets],
                    return_exceptions=True
                )


    async def connect(
            self, 
            websocket: WebSocket,
            tickers: list[str],
            fields: list[str],
    ):
        """
        Here we manage market data subscription from ticker level (ticker as key and cid).
        """
        for ticker in tickers:
            if ticker not in self.ticker_to_fields:
                # New ticker
                self.ticker_to_websockets[ticker] = {websocket}
                self.ticker_to_fields[ticker] = set(fields)

                # Subscribe
                cid = blpapi.CorrelationId(ticker)
                sub = blpapi.SubscriptionList()
                sub.add(topic=ticker, fields=fields, correlationId=cid)
                self.session.subscribe(sub)

            else:
                # Exisiting ticker
                self.ticker_to_websockets[ticker].add(websocket)

                additional_fields = set(fields) - self.ticker_to_fields[ticker]

                if additional_fields:
                    self.ticker_to_fields[ticker].union(fields)
                    # Resubscribe
                    cid = blpapi.CorrelationId(ticker)
                    resub = blpapi.SubscriptionList()
                    resub.add(topic=ticker, fields=self.ticker_to_fields[ticker], correlationId=cid)
                    self.session.resubscribe(resub)


    async def disconnect(self, websocket: WebSocket, tickers: list[str]):
        """Disconnect the WebSocket from a list of tickers' subscription"""
        for ticker in tickers:
            if ticker in self.ticker_to_websockets:
                self.ticker_to_websockets[ticker].discard(websocket)
                if not self.ticker_to_websockets[ticker]: # No more subscribers for this topic
                    # Unsub
                    cid = blpapi.CorrelationId(ticker)
                    unsub = blpapi.SubscriptionList()
                    unsub.add(topic=ticker, correlationId=cid)
                    self.session.unsubscribe(unsub)
                    logger.info(f"Unsubscribed from Bloomberg for ticker: {ticker}")
                    # Clean up
                    del self.ticker_to_fields[ticker]
                    del self.ticker_to_websockets[ticker]
