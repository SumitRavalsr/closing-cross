import asyncio
import os
import socket
import stat
from functools import partial
from pathlib import Path

import anyio
from mcp.server.lowlevel import Server
from mcp.shared.message import SessionMessage
from mcp.types import JSONRPCMessage
from pydantic import ValidationError


def _remove_stale_socket(path: Path) -> None:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return
    if not stat.S_ISSOCK(mode):
        raise RuntimeError(f'MCP socket path is occupied by a non-socket file: {path}')
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as probe:
        probe.settimeout(1)
        try:
            probe.connect(str(path))
        except ConnectionRefusedError:
            path.unlink()
            return
    raise RuntimeError(f'An MCP service is already listening on {path}')


async def serve_connection(server: Server, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    incoming, read_stream = anyio.create_memory_object_stream[SessionMessage | Exception](0)
    write_stream, outgoing = anyio.create_memory_object_stream[SessionMessage](0)

    async def receive() -> None:
        async with incoming:
            try:
                while line := await reader.readline():
                    try:
                        message = JSONRPCMessage.model_validate_json(line)
                    except ValidationError as error:
                        await incoming.send(error)
                    else:
                        await incoming.send(SessionMessage(message))
            except (ConnectionError, ValueError, anyio.BrokenResourceError):
                return

    async def send() -> None:
        async with outgoing:
            try:
                async for message in outgoing:
                    payload = message.message.model_dump_json(by_alias=True, exclude_none=True)
                    writer.write(payload.encode() + b'\n')
                    await writer.drain()
            except ConnectionError:
                writer.close()

    try:
        async with read_stream, write_stream, anyio.create_task_group() as tasks:
            tasks.start_soon(receive)
            tasks.start_soon(send)
            try:
                await server.run(read_stream, write_stream, server.create_initialization_options())
            finally:
                tasks.cancel_scope.cancel()
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except ConnectionError:
            pass

async def serve_socket(server: Server, path: Path) -> None:
    _remove_stale_socket(path)
    previous_umask = os.umask(0o007)
    try:
        listener = await asyncio.start_unix_server(
            partial(serve_connection, server), path, limit=1_048_576, start_serving=False,
        )
    finally:
        os.umask(previous_umask)
    try:
        async with listener:
            path.chmod(0o660)
            await listener.serve_forever()
    finally:
        path.unlink(missing_ok=True)
