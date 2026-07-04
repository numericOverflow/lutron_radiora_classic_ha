"""URL-dispatching async transport for RadioRA Classic.

Supports:
- socket://host:port  — Raw TCP (ser2net raw mode, FakeController)
- rfc2217://host:port — RFC 2217 via pyserial in executor thread
- /dev/ttyUSB0        — Local serial via pyserial-asyncio-fast
"""

from __future__ import annotations

import asyncio
import urllib.parse

from .exceptions import RadioRAConnectionError, RadioRAConnectionLost


class AsyncTransport:
    """Base async transport interface."""

    async def readline(self) -> bytes:
        """Read until CR delimiter."""
        raise NotImplementedError  # pragma: no cover

    async def write(self, data: bytes) -> None:
        """Write bytes to transport."""
        raise NotImplementedError  # pragma: no cover

    async def close(self) -> None:
        """Close transport."""
        raise NotImplementedError  # pragma: no cover

    @property
    def connected(self) -> bool:
        """Whether transport is connected."""
        raise NotImplementedError  # pragma: no cover

    @classmethod
    async def connect(cls, url: str) -> AsyncTransport:
        """Connect to the specified URL, returning appropriate transport."""
        parsed = urllib.parse.urlparse(url)

        if parsed.scheme in ("socket", "tcp"):
            return await _TCPTransport.create(parsed.hostname or "localhost", parsed.port or 4000)
        elif parsed.scheme == "rfc2217":
            return await _RFC2217Transport.create(url)
        else:
            return await _LocalSerialTransport.create(url)


class _TCPTransport(AsyncTransport):
    """Raw TCP via asyncio streams. Fastest path."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self._reader = reader
        self._writer = writer
        self._connected = True

    @classmethod
    async def create(cls, host: str, port: int) -> _TCPTransport:
        try:
            reader, writer = await asyncio.open_connection(host, port)
        except OSError as err:
            raise RadioRAConnectionError(f"TCP connect failed: {err}") from err
        return cls(reader, writer)

    async def readline(self) -> bytes:
        try:
            data = await self._reader.readuntil(b"\r")
        except (asyncio.IncompleteReadError, ConnectionError, OSError) as err:
            self._connected = False
            raise RadioRAConnectionLost(f"Read failed: {err}") from err
        return data

    async def write(self, data: bytes) -> None:
        try:
            self._writer.write(data)
            await self._writer.drain()
        except (ConnectionError, OSError) as err:
            self._connected = False
            raise RadioRAConnectionLost(f"Write failed: {err}") from err

    async def close(self) -> None:
        self._connected = False
        try:
            self._writer.close()
            await self._writer.wait_closed()
        except OSError:
            pass

    @property
    def connected(self) -> bool:
        return self._connected and not self._writer.is_closing()


class _RFC2217Transport(AsyncTransport):
    """RFC 2217 via pyserial sync wrapped in executor threads."""

    def __init__(self, serial_instance: object) -> None:
        import serial

        self._serial: serial.Serial = serial_instance  # type: ignore[assignment]
        self._connected = True

    @classmethod
    async def create(cls, url: str) -> _RFC2217Transport:
        import serial

        try:
            serial_instance = await asyncio.to_thread(
                serial.serial_for_url, url, baudrate=9600, timeout=2
            )
        except Exception as err:
            raise RadioRAConnectionError(f"RFC2217 connect failed: {err}") from err
        return cls(serial_instance)

    async def readline(self) -> bytes:
        try:
            data: bytes = await asyncio.to_thread(self._serial.read_until, b"\r")
        except Exception as err:
            self._connected = False
            raise RadioRAConnectionLost(f"RFC2217 read failed: {err}") from err
        if not data:
            raise RadioRAConnectionLost("RFC2217 read returned empty (timeout/disconnect)")
        return data

    async def write(self, data: bytes) -> None:
        try:
            await asyncio.to_thread(self._serial.write, data)
        except Exception as err:
            self._connected = False
            raise RadioRAConnectionLost(f"RFC2217 write failed: {err}") from err

    async def close(self) -> None:
        self._connected = False
        try:
            await asyncio.to_thread(self._serial.close)
        except OSError:
            pass

    @property
    def connected(self) -> bool:
        return self._connected


class _LocalSerialTransport(AsyncTransport):
    """Local serial port via pyserial-asyncio-fast."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self._reader = reader
        self._writer = writer
        self._connected = True

    @classmethod
    async def create(cls, url: str) -> _LocalSerialTransport:
        try:
            import serial_asyncio_fast

            reader, writer = await serial_asyncio_fast.open_serial_connection(
                url=url, baudrate=9600
            )
        except Exception as err:
            raise RadioRAConnectionError(f"Serial connect failed: {err}") from err
        return cls(reader, writer)

    async def readline(self) -> bytes:
        try:
            data = await self._reader.readuntil(b"\r")
        except (asyncio.IncompleteReadError, ConnectionError, OSError) as err:
            self._connected = False
            raise RadioRAConnectionLost(f"Serial read failed: {err}") from err
        return data

    async def write(self, data: bytes) -> None:
        try:
            self._writer.write(data)
            await self._writer.drain()
        except (ConnectionError, OSError) as err:
            self._connected = False
            raise RadioRAConnectionLost(f"Serial write failed: {err}") from err

    async def close(self) -> None:
        self._connected = False
        try:
            self._writer.close()
        except OSError:
            pass

    @property
    def connected(self) -> bool:
        return self._connected
