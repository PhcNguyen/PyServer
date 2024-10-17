# Copyright (C) PhcNguyen Developers
# Distributed under the terms of the Modified BSD License.

import asyncio
from typing import List, Tuple

from sources.model import types
from sources.configs.network import NetworkConfigs
from sources.manager.firewall import FireWall
from sources.model.logging.serverlogger import AsyncLogger
from sources.application.server.tcpsession import TcpSession



class TcpServer(NetworkConfigs):
    def __init__(self, host: str, port: int, sql: types.DatabaseManager):
        self.stop_event = asyncio.Event()
        self.firewall = FireWall()
        self.server_address: Tuple[str, int] = (host, port)
        self.running: bool = False
        self.client_handler = ClientHandler(self.firewall, sql)

    async def start(self):
        """Start the server and listen for incoming connections asynchronously."""
        if self.running:
            await AsyncLogger.notify("Server is already running.")
            return

        try:
            await AsyncLogger.notify(f'Starting async server at {self.server_address}')
            self.running = True

            server = await asyncio.start_server(
                self.client_handler.handle_client, *self.server_address,
                reuse_address=True
            )

            asyncio.create_task(self.firewall.auto_unblock_ips())

            async with server:
                await server.serve_forever()
        except OSError as error:
            await AsyncLogger.notify_error(f"OSError: {str(error)} - {self.server_address}")
            await asyncio.sleep(5)  # Retry after 5 seconds
        except Exception as error:
            await AsyncLogger.notify_error(str(error))

    async def stop(self):
        """Stop the server asynchronously."""
        if not self.running:
            return

        self.running = False
        await self.client_handler.close_all_connections()
        await AsyncLogger.notify('Server stopped.')



class ClientHandler:
    def __init__(self, firewall: FireWall, sql: types.DatabaseManager):
        self.firewall = firewall
        self.sql = sql
        self.client_connections: List[TcpSession] = []  # Store TcpSession objects

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Handle data from a client asynchronously with timeout."""
        client_address = writer.get_extra_info('peername')

        if client_address[0] in self.firewall.block_ips:
            writer.close()
            await writer.wait_closed()
            return

        if len(self.client_connections) >= TcpServer.MAX_CONNECTIONS:
            await AsyncLogger.notify_error(f"Connection limit exceeded. Refusing connection from {client_address}")
            writer.close()
            await writer.wait_closed()
            return

        # Create TcpSession for the connected client
        session = TcpSession(self, self.sql)
        await session.connect(reader, writer)
        self.client_connections.append(session)
        await AsyncLogger.notify(f"Client connected from {client_address}")

        try:
            while session.is_connected:  # Ensure this attribute exists in TcpSession
                await asyncio.sleep(1)  # Keep the session alive
        finally:
            await self.close_connection(session)
            await AsyncLogger.notify(f"Connection with {client_address} closed.")

    async def close_connection(self, session: TcpSession):
        """Close a client connection."""
        await session.disconnect()  # Close the session properly
        self.client_connections.remove(session)

    async def close_all_connections(self):
        """Close all client connections."""
        close_tasks = [self.close_connection(session) for session in self.client_connections]
        await asyncio.gather(*close_tasks)
        self.client_connections.clear()