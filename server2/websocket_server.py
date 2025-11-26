#!/usr/bin/env python3

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Dict, Set, Optional
import websockets
from websockets.exceptions import ConnectionClosed
import aiofiles

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Program2Interface:
    """Interface for Program-2 to interact with the system"""
    
    def __init__(self, websocket_router):
        self.websocket_router = websocket_router
        self.topics: Dict[str, str] = {}  # topic_name -> session_id
        self.topic_owners: Dict[str, object] = {}  # topic_name -> client websocket
        
    async def create_topic(self, topic_name: str, user_id: str, client_websocket=None) -> bool:
        """Create a new topic and start a session"""
        try:
            # Create topic directory
            data_dir = os.getenv('DATA_DIR', './data')
            topic_dir = f"{data_dir}/topics/{topic_name}"
            os.makedirs(topic_dir, exist_ok=True)
            
            # Request session creation from server-1
            session_id = await self.websocket_router.request_session_creation(user_id)
            
            if session_id:
                # Store topic mapping
                self.topics[topic_name] = session_id
                
                # Store the client that owns this topic
                if client_websocket:
                    self.topic_owners[topic_name] = client_websocket
                
                # Log session opened
                await self.log_to_topic(topic_name, f"session opened - {session_id}")
                
                logger.info(f"Created topic {topic_name} with session {session_id}")
                return True
            else:
                logger.error(f"Failed to create session for topic {topic_name}")
                return False
                
        except Exception as e:
            logger.error(f"Error creating topic {topic_name}: {e}")
            return False
            
    async def stop_topic(self, topic_name: str) -> bool:
        """Stop a topic and destroy its session"""
        session_id = self.topics.get(topic_name)
        if not session_id:
            logger.error(f"Topic {topic_name} not found")
            return False
            
        try:
            # Request session destruction
            await self.websocket_router.request_session_destruction(session_id)
            
            # Log session stopped
            await self.log_to_topic(topic_name, "стоп")
            
            # Remove from topics
            del self.topics[topic_name]
            
            # Clean up client ownership
            if topic_name in self.topic_owners:
                del self.topic_owners[topic_name]
            
            logger.info(f"Stopped topic {topic_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error stopping topic {topic_name}: {e}")
            return False
            
    async def send_command_to_topic(self, topic_name: str, command: str) -> bool:
        """Send a command to a topic's session"""
        session_id = self.topics.get(topic_name)
        if not session_id:
            logger.error(f"Topic {topic_name} not found")
            return False
            
        try:
            # Send command to session
            await self.websocket_router.send_command_to_session(session_id, command)
            
            # Log command
            await self.log_to_topic(topic_name, f"COMMAND: {command}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error sending command to topic {topic_name}: {e}")
            return False
            
    async def handle_session_output(self, session_id: str, output: str):
        """Handle output from a session"""
        # Find topic for this session
        topic_name = None
        for topic, sid in self.topics.items():
            if sid == session_id:
                topic_name = topic
                break
                
        if topic_name:
            await self.log_to_topic(topic_name, f"OUTPUT: {output}")
            logger.info(f"Logged output for topic {topic_name}: {output[:100]}...")
            
            # Send output only to the client that owns this topic
            await self.send_output_to_owner(topic_name, output)
            
    async def send_output_to_owner(self, topic_name: str, output: str):
        """Send output only to the client that owns this topic"""
        if topic_name not in self.topic_owners:
            return
            
        owner_client = self.topic_owners[topic_name]
        if not owner_client:
            return
            
        # Create output message for the owner client
        message = {
            "type": "output",
            "topicName": topic_name,
            "data": output,
            "timestamp": datetime.now().isoformat()
        }
        
        try:
            await owner_client.send(json.dumps(message))
            logger.debug(f"Sent output to owner of topic {topic_name}")
        except Exception as e:
            logger.warning(f"Failed to send output to topic owner: {e}")
            # Remove the disconnected client
            del self.topic_owners[topic_name]
            
    async def log_to_topic(self, topic_name: str, message: str):
        """Log a message to topic's log file"""
        try:
            data_dir = os.getenv('DATA_DIR', './data')
            log_file = f"{data_dir}/topics/{topic_name}/{topic_name}.log"
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_entry = f"{timestamp} - {message}\n"
            
            async with aiofiles.open(log_file, 'a') as f:
                await f.write(log_entry)
                
        except Exception as e:
            logger.error(f"Error logging to topic {topic_name}: {e}")


class WebSocketRouter:
    """WebSocket router for handling connections and message routing"""
    
    def __init__(self):
        self.server1_connection: Optional[websockets.WebSocketServerProtocol] = None
        self.client_connections: Set[websockets.WebSocketServerProtocol] = set()
        self.program2: Optional[Program2Interface] = None
        
    def set_program2_interface(self, program2: Program2Interface):
        """Set the Program-2 interface"""
        self.program2 = program2
        
    async def handle_server1_connection(self, websocket, path):
        """Handle connection from server-1"""
        logger.info("Server-1 connected")
        self.server1_connection = websocket
        
        try:
            async for message in websocket:
                await self.handle_server1_message(message)
        except ConnectionClosed:
            logger.warning("Server-1 disconnected")
            self.server1_connection = None
        except Exception as e:
            logger.error(f"Error in server-1 connection: {e}")
            self.server1_connection = None
            
    async def handle_server1_message(self, message: str):
        """Handle message from server-1"""
        try:
            data = json.loads(message)
            message_type = data.get('type')
            
            if message_type == 'stdout':
                session_id = data.get('sessionId')
                output = data.get('data')
                
                if session_id and output and self.program2:
                    await self.program2.handle_session_output(session_id, output)
                    
            elif message_type == 'session_created':
                # Handle session creation response
                session_id = data.get('sessionId')
                logger.info(f"Session created: {session_id}")
                
            elif message_type == 'session_destroyed':
                # Handle session destruction response
                session_id = data.get('sessionId')
                logger.info(f"Session destroyed: {session_id}")
                
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON from server-1: {message}")
        except Exception as e:
            logger.error(f"Error handling server-1 message: {e}")
            
    async def handle_client_connection(self, websocket, path):
        """Handle client connections (for Program-2)"""
        logger.info(f"Client connected: {path}")
        self.client_connections.add(websocket)
        
        try:
            async for message in websocket:
                await self.handle_client_message(websocket, message)
        except ConnectionClosed:
            logger.info("Client disconnected")
        except Exception as e:
            logger.error(f"Error in client connection: {e}")
        finally:
            self.client_connections.discard(websocket)
            
    async def handle_client_message(self, websocket, message: str):
        """Handle message from client"""
        try:
            data = json.loads(message)
            command_type = data.get('type')
            
            if command_type == 'create_topic':
                topic_name = data.get('topicName')
                user_id = data.get('userId')
                
                if topic_name and user_id and self.program2:
                    success = await self.program2.create_topic(topic_name, user_id, websocket)
                    response = {
                        'type': 'topic_created' if success else 'topic_create_failed',
                        'topicName': topic_name,
                        'success': success
                    }
                    await websocket.send(json.dumps(response))
                    
            elif command_type == 'stop_topic':
                topic_name = data.get('topicName')
                
                if topic_name and self.program2:
                    success = await self.program2.stop_topic(topic_name)
                    response = {
                        'type': 'topic_stopped',
                        'topicName': topic_name,
                        'success': success
                    }
                    await websocket.send(json.dumps(response))
                    
            elif command_type == 'send_command':
                topic_name = data.get('topicName')
                command = data.get('command')
                
                if topic_name and command and self.program2:
                    success = await self.program2.send_command_to_topic(topic_name, command)
                    response = {
                        'type': 'command_sent',
                        'topicName': topic_name,
                        'command': command,
                        'success': success
                    }
                    await websocket.send(json.dumps(response))
                    
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON from client: {message}")
        except Exception as e:
            logger.error(f"Error handling client message: {e}")
            
    async def request_session_creation(self, user_id: str) -> Optional[str]:
        """Request session creation from server-1"""
        if not self.server1_connection:
            logger.error("No connection to server-1")
            return None
            
        # For this implementation, we'll make HTTP request to server-1
        # In a real implementation, this could be done via WebSocket
        import aiohttp
        
        try:
            async with aiohttp.ClientSession() as session:
                server1_url = os.getenv('SERVER1_URL', 'http://localhost:8004')
                async with session.post(
                    f'{server1_url}/sessions',
                    json={'user_id': user_id}
                ) as response:
                    if response.status == 201:
                        data = await response.json()
                        return data.get('session_id')
                    else:
                        logger.error(f"Failed to create session: {response.status}")
                        return None
                        
        except Exception as e:
            logger.error(f"Error requesting session creation: {e}")
            return None
            
    async def request_session_destruction(self, session_id: str):
        """Request session destruction from server-1"""
        if not self.server1_connection:
            logger.error("No connection to server-1")
            return
            
        # Send destruction command via WebSocket
        message = {
            'type': 'session_destroy',
            'sessionId': session_id,
            'timestamp': datetime.now(timezone.utc).isoformat() + 'Z'
        }
        
        try:
            await self.server1_connection.send(json.dumps(message))
        except Exception as e:
            logger.error(f"Error requesting session destruction: {e}")
            
    async def send_command_to_session(self, session_id: str, command: str):
        """Send command to session via server-1"""
        if not self.server1_connection:
            logger.error("No connection to server-1")
            return
            
        message = {
            'type': 'command',
            'sessionId': session_id,
            'data': command,
            'timestamp': datetime.now(timezone.utc).isoformat() + 'Z'
        }
        
        try:
            await self.server1_connection.send(json.dumps(message))
        except Exception as e:
            logger.error(f"Error sending command to session: {e}")


async def start_servers():
    """Start the WebSocket servers"""
    router = WebSocketRouter()
    program2 = Program2Interface(router)
    router.set_program2_interface(program2)
    
    # Create data directory (use local directory for testing)
    data_dir = os.getenv('DATA_DIR', './data')
    os.makedirs(f"{data_dir}/topics", exist_ok=True)
    
    # Get ports from environment for flexibility
    server1_port = int(os.getenv('SERVER1_WS_PORT', '8003'))
    client_port = int(os.getenv('CLIENT_WS_PORT', '8083'))
    
    # Get WebSocket timeout settings from environment
    ping_interval = int(os.getenv('WS_PING_INTERVAL', '300'))  # 5 minutes default
    ping_timeout = int(os.getenv('WS_PING_TIMEOUT', '60'))     # 1 minute default
    
    # Start WebSocket server for server-1 connections
    server1_server = await websockets.serve(
        router.handle_server1_connection,
        '0.0.0.0',
        server1_port,
        ping_interval=ping_interval,
        ping_timeout=ping_timeout
    )
    
    # Start WebSocket server for client connections
    client_server = await websockets.serve(
        router.handle_client_connection,
        '0.0.0.0',
        client_port,
        ping_interval=ping_interval,
        ping_timeout=ping_timeout
    )
    
    logger.info("Server-2 started:")
    logger.info(f"  - Server-1 WebSocket: port {server1_port}")
    logger.info(f"  - Client WebSocket: port {client_port}")
    logger.info(f"  - WebSocket ping interval: {ping_interval}s")
    logger.info(f"  - WebSocket ping timeout: {ping_timeout}s")
    
    # Keep servers running
    await asyncio.gather(
        server1_server.wait_closed(),
        client_server.wait_closed()
    )


if __name__ == "__main__":
    try:
        asyncio.run(start_servers())
    except KeyboardInterrupt:
        logger.info("Shutting down...")