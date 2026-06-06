import threading


class Readiness:
    def __init__(self):
        self._blpapi = False
        self._lock = threading.Lock()

    @property
    def blpapi(self) -> bool:
        with self._lock:
            return self._blpapi

    @blpapi.setter
    def blpapi(self, value: bool) -> None:
        with self._lock:
            self._blpapi = value