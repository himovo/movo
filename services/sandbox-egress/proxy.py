"""HTTP CONNECT proxy for public and private destinations.

Dependency builds use an internal-only Docker network and reach this proxy by
name. Script runtimes may also use the proxy for HTTP and SSH connections.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit


MAX_HEADER = 16 * 1024
MAX_CONNECTIONS = 256
_slots = asyncio.Semaphore(MAX_CONNECTIONS)


def _allowed_destination(ip: ipaddress.IPv4Address | ipaddress.IPv6Address, port: int) -> bool:
    if ip.is_global:
        return True
    if ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_unspecified:
        return False
    return ip.is_private


async def _resolved_destination(host: str, port: int) -> tuple[str, int]:
    if not host or not 1 <= port <= 65535:
        raise ValueError("Invalid destination")
    records = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    for _, _, _, _, address in records:
        ip = ipaddress.ip_address(address[0])
        if _allowed_destination(ip, port):
            return str(ip), port
    raise PermissionError("Destination is not allowed")


async def _pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while data := await reader.read(65536):
            writer.write(data)
            await writer.drain()
    except (ConnectionError, OSError):
        pass
    finally:
        try:
            writer.write_eof()
        except (OSError, RuntimeError):
            pass


async def _handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    async with _slots:
        upstream = None
        try:
            header = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=15)
            if len(header) > MAX_HEADER:
                raise ValueError("Request headers are too large")
            lines = header.split(b"\r\n")
            method, target, _ = lines[0].decode("ascii").split(" ", 2)
            if method == "CONNECT":
                host, separator, port_text = target.rpartition(":")
                if not separator or not port_text.isdigit():
                    raise ValueError("Invalid CONNECT target")
                address = await _resolved_destination(host.strip("[]"), int(port_text))
                upstream_reader, upstream_writer = await asyncio.wait_for(asyncio.open_connection(*address), timeout=15)
                upstream = upstream_writer
                writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            elif method in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}:
                url = urlsplit(target)
                if url.scheme != "http" or not url.hostname or url.username or url.password:
                    raise ValueError("Only plain HTTP absolute URLs are accepted")
                address = await _resolved_destination(url.hostname, url.port or 80)
                upstream_reader, upstream_writer = await asyncio.wait_for(asyncio.open_connection(*address), timeout=15)
                upstream = upstream_writer
                path = (url.path or "/") + (f"?{url.query}" if url.query else "")
                upstream_writer.write(f"{method} {path} HTTP/1.1\r\n".encode("ascii") + b"\r\n".join(lines[1:]))
            else:
                raise ValueError("Unsupported proxy method")
            await upstream_writer.drain()
            await asyncio.gather(_pipe(reader, upstream_writer), _pipe(upstream_reader, writer))
        except (ValueError, PermissionError, asyncio.TimeoutError, asyncio.LimitOverrunError, OSError):
            writer.write(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
        finally:
            if upstream is not None:
                upstream.close()
            writer.close()
            await writer.wait_closed()


async def main() -> None:
    server = await asyncio.start_server(_handle, "0.0.0.0", 3128, limit=MAX_HEADER)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
