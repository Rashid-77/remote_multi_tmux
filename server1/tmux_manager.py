#!/usr/bin/env python3

import asyncio
import subprocess
import uuid
import json
import os
import logging
from datetime import datetime
from typing import Dict, Optional
import websockets
from websockets.exceptions import ConnectionClosed

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TmuxSessionManager:
    def __init__(self, session_name: str = "worker_sessions"):
        self.session_name = session_name
        self.sessions: Dict[str, str] = {}  # session_id -> window_name
        self.websocket = None
        self.sequence = 0
        
    async def start(self):
        """Initialize tmux session and connect to server-2"""
        # Create main tmux session if it doesn't exist
        try:
            subprocess.run(
                ["tmux", "has-session", "-t", self.session_name], 
                check=True, 
                capture_output=True
            )
        except subprocess.CalledProcessError:
            subprocess.run(
                ["tmux", "new-session", "-d", "-s", self.session_name],
                check=True
            )
        
        # Connect to server-2 WebSocket
        await self.connect_websocket()
        
    async def connect_websocket(self):
        """Connect to server-2 WebSocket"""
        server2_url = os.getenv('SERVER2_URL', 'ws://localhost:8003/ws')
        max_retries = 5
        retry_delay = 2
        
        for attempt in range(max_retries):
            try:
                self.websocket = await websockets.connect(server2_url)
                logger.info(f"Connected to server-2 at {server2_url}")
                
                # Start listening for messages
                asyncio.create_task(self.listen_for_messages())
                break
                
            except Exception as e:
                logger.warning(f"Connection attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                else:
                    logger.error("Failed to connect to server-2 after all retries")
                    raise
                    
    async def listen_for_messages(self):
        """Listen for commands from server-2"""
        try:
            async for message in self.websocket:
                try:
                    data = json.loads(message)
                    await self.handle_command(data)
                except json.JSONDecodeError:
                    logger.error(f"Invalid JSON received: {message}")
                except Exception as e:
                    logger.error(f"Error handling message: {e}")
                    
        except ConnectionClosed:
            logger.warning("WebSocket connection closed")
            # Try to reconnect
            await asyncio.sleep(2)
            await self.connect_websocket()
            
    async def handle_command(self, data: dict):
        """Handle command from server-2"""
        command_type = data.get('type')
        session_id = data.get('sessionId')
        command = data.get('data')
        
        if command_type == 'command' and session_id and command:
            await self.send_command_to_session(session_id, command)
        elif command_type == 'session_destroy' and session_id:
            await self.destroy_session(session_id)
            
    async def create_session(self, user_id: str) -> str:
        """Create a new tmux session"""
        session_id = str(uuid.uuid4())
        window_name = f"worker-{session_id[:8]}"
        
        try:
            # Create directory for session
            os.makedirs(f"/tmp/sessions/{session_id}", exist_ok=True)
            
            # Create new tmux window
            subprocess.run([
                "tmux", "new-window", 
                "-t", self.session_name,
                "-n", window_name,
                "bash"  # Start with bash shell
            ], check=True)
            
            # Send initial start command
            await self.send_command_to_window(window_name, 'echo "старт"')
            
            # Store session
            self.sessions[session_id] = window_name
            
            # Start monitoring this session
            asyncio.create_task(self.monitor_session_output(session_id))
            
            logger.info(f"Created session {session_id} for user {user_id}")
            return session_id
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to create tmux session: {e}")
            raise Exception("Failed to create session")
            
    async def send_command_to_session(self, session_id: str, command: str):
        """Send command to specific session"""
        window_name = self.sessions.get(session_id)
        if not window_name:
            logger.error(f"Session {session_id} not found")
            return
            
        await self.send_command_to_window(window_name, command)
        
    async def send_command_to_window(self, window_name: str, command: str):
        """Send command to tmux window"""
        try:
            subprocess.run([
                "tmux", "send-keys",
                "-t", f"{self.session_name}:{window_name}",
                command, "Enter"
            ], check=True)
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to send command to {window_name}: {e}")
            
    async def monitor_session_output(self, session_id: str):
        """Monitor output from a tmux session"""
        window_name = self.sessions.get(session_id)
        if not window_name:
            return
            
        last_output = ""
        
        while session_id in self.sessions:
            try:
                # Capture pane content
                result = subprocess.run([
                    "tmux", "capture-pane",
                    "-t", f"{self.session_name}:{window_name}",
                    "-p"
                ], capture_output=True, text=True, check=True)
                
                current_output = result.stdout.strip()
                
                # Only send new output
                if current_output != last_output:
                    # Find new lines
                    if last_output:
                        last_lines = last_output.split('\n')
                        current_lines = current_output.split('\n')
                        
                        # Find new lines by comparing from the end
                        new_lines = []
                        for i, line in enumerate(current_lines):
                            if i >= len(last_lines) or line != last_lines[i]:
                                new_lines.extend(current_lines[i:])
                                break
                        
                        if new_lines:
                            new_output = '\n'.join(new_lines)
                            await self.send_output_to_server2(session_id, new_output)
                    else:
                        await self.send_output_to_server2(session_id, current_output)
                    
                    last_output = current_output
                
                await asyncio.sleep(0.5)  # Poll every 500ms
                
            except subprocess.CalledProcessError:
                # Session might be closed
                break
            except Exception as e:
                logger.error(f"Error monitoring session {session_id}: {e}")
                break
                
    async def send_output_to_server2(self, session_id: str, output: str):
        """Send session output to server-2"""
        if not self.websocket:
            return
            
        message = {
            "type": "stdout",
            "sessionId": session_id,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "data": output,
            "sequence": self.sequence
        }
        
        self.sequence += 1
        
        try:
            await self.websocket.send(json.dumps(message))
        except Exception as e:
            logger.error(f"Failed to send output to server-2: {e}")
            
    async def destroy_session(self, session_id: str) -> bool:
        """Destroy a tmux session"""
        window_name = self.sessions.get(session_id)
        if not window_name:
            logger.error(f"Session {session_id} not found")
            return False
            
        try:
            # Kill tmux window
            subprocess.run([
                "tmux", "kill-window",
                "-t", f"{self.session_name}:{window_name}"
            ], check=True)
            
            # Remove from sessions
            del self.sessions[session_id]
            
            # Clean up session directory
            import shutil
            shutil.rmtree(f"/tmp/sessions/{session_id}", ignore_errors=True)
            
            logger.info(f"Destroyed session {session_id}")
            return True
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to destroy session {session_id}: {e}")
            return False


class TmuxHTTPServer:
    def __init__(self, tmux_manager: TmuxSessionManager, port: int = 8001):
        self.tmux_manager = tmux_manager
        self.port = port
        
    async def handle_request(self, request):
        """Handle HTTP requests"""
        from aiohttp import web
        
        if request.method == 'POST' and request.path == '/sessions':
            return await self.create_session(request)
        elif request.method == 'DELETE' and request.path.startswith('/sessions/'):
            session_id = request.path.split('/')[-1]
            return await self.delete_session(session_id)
        else:
            return web.Response(status=404, text="Not found")
            
    async def create_session(self, request):
        """Handle session creation"""
        from aiohttp import web
        
        try:
            data = await request.json()
            user_id = data.get('user_id')
            
            if not user_id:
                return web.json_response({'error': 'user_id required'}, status=400)
                
            session_id = await self.tmux_manager.create_session(user_id)
            
            response_data = {
                'session_id': session_id,
                'created_at': datetime.utcnow().isoformat() + 'Z',
                'websocket_endpoint': f'ws://server2:8000/ws/{session_id}',
                'websocket_token': 'dummy_token'
            }
            
            return web.json_response(response_data, status=201)
            
        except Exception as e:
            logger.error(f"Error creating session: {e}")
            return web.json_response({'error': 'Failed to create session'}, status=422)
            
    async def delete_session(self, session_id: str):
        """Handle session deletion"""
        from aiohttp import web
        
        try:
            success = await self.tmux_manager.destroy_session(session_id)
            if success:
                return web.Response(status=204)
            else:
                return web.json_response({'error': 'Session not found'}, status=404)
        except Exception as e:
            logger.error(f"Error deleting session: {e}")
            return web.json_response({'error': 'Internal error'}, status=500)


async def main():
    """Main entry point"""
    tmux_manager = TmuxSessionManager()
    http_server = TmuxHTTPServer(tmux_manager)
    
    # Start tmux manager
    await tmux_manager.start()
    
    # Start HTTP server
    from aiohttp import web
    app = web.Application()
    app.router.add_post('/sessions', http_server.create_session)
    app.router.add_delete('/sessions/{session_id}', http_server.delete_session)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8001)
    await site.start()
    
    logger.info("Server-1 started on port 8001")
    
    # Keep running
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())