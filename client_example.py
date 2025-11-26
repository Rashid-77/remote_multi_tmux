#!/usr/bin/env python3

import asyncio
import json
import os
import websockets
import sys

class Program1Client:
    """Example Program-1 client that demonstrates the system"""
    
    def __init__(self, server2_url="ws://localhost:8082"):
        self.server2_url = server2_url
        self.websocket = None
        self.current_topic = None
        
    async def connect(self):
        """Connect to server-2"""
        try:
            # Configure longer timeout for WebSocket connection
            ping_interval = int(os.getenv('WS_PING_INTERVAL', '300'))  # 5 minutes
            ping_timeout = int(os.getenv('WS_PING_TIMEOUT', '60'))     # 1 minute
            
            self.websocket = await websockets.connect(
                self.server2_url,
                ping_interval=ping_interval,
                ping_timeout=ping_timeout
            )
            print(f"Connected to server-2 at {self.server2_url}")
            print(f"WebSocket timeout: ping_interval={ping_interval}s, ping_timeout={ping_timeout}s")
            
            # Start listening for responses
            asyncio.create_task(self.listen_for_responses())
            
        except Exception as e:
            print(f"Failed to connect to server-2: {e}")
            return False
        return True
        
    async def listen_for_responses(self):
        """Listen for responses from server-2"""
        try:
            async for message in self.websocket:
                try:
                    data = json.loads(message)
                    await self.handle_response(data)
                except json.JSONDecodeError:
                    print(f"Invalid response: {message}")
                except Exception as e:
                    print(f"Error handling response: {e}")
        except websockets.exceptions.ConnectionClosed as e:
            print(f"⚠️  Connection to server-2 closed: {e}")
        except Exception as e:
            print(f"⚠️  Error in response listener: {e}")
            
    async def handle_response(self, data):
        """Handle response from server-2"""
        response_type = data.get('type')
        
        if response_type == 'topic_created':
            topic_name = data.get('topicName')
            success = data.get('success')
            if success:
                print(f"✓ Topic '{topic_name}' created successfully")
                self.current_topic = topic_name
            else:
                print(f"✗ Failed to create topic '{topic_name}'")
                
        elif response_type == 'topic_create_failed':
            topic_name = data.get('topicName')
            print(f"✗ Failed to create topic '{topic_name}' - невозможно создать сессию")
            
        elif response_type == 'topic_stopped':
            topic_name = data.get('topicName')
            success = data.get('success')
            if success:
                print(f"✓ Topic '{topic_name}' stopped")
                self.current_topic = None
            else:
                print(f"✗ Failed to stop topic '{topic_name}'")
                
        elif response_type == 'command_sent':
            topic_name = data.get('topicName')
            command = data.get('command')
            success = data.get('success')
            if success:
                print(f"✓ Command '{command}' sent to topic '{topic_name}'")
            else:
                print(f"✗ Failed to send command '{command}' to topic '{topic_name}'")

        elif response_type == 'output':
            topic_name = data.get('topicName')
            output = data.get('data')
            timestamp = data.get('timestamp', '')
            if output and topic_name == self.current_topic:
                # Display the output with a prefix to distinguish from local messages
                print(f"📤 {output.strip()}")
        else:
            print(f"Unknown response type: {response_type}")
            
    async def create_topic(self, topic_name, user_id):
        """Create a new topic (implements use case 1)"""
        if not self.websocket:
            print("Not connected to server-2")
            return False
            
        message = {
            "type": "create_topic",
            "topicName": topic_name,
            "userId": user_id
        }
        
        await self.websocket.send(json.dumps(message))
        return True
        
    async def stop_topic(self, topic_name=None):
        """Stop a topic (implements use case 3)"""
        if not self.websocket:
            print("Not connected to server-2")
            return False
            
        if not topic_name:
            topic_name = self.current_topic
            
        if not topic_name:
            print("No topic to stop")
            return False
            
        message = {
            "type": "stop_topic",
            "topicName": topic_name
        }
        
        await self.websocket.send(json.dumps(message))
        return True
        
    async def send_command(self, command, topic_name=None):
        """Send command to topic (implements use case 4)"""
        if not self.websocket:
            print("Not connected to server-2")
            return False
            
        if not topic_name:
            topic_name = self.current_topic
            
        if not topic_name:
            print("No active topic")
            return False
            
        message = {
            "type": "send_command",
            "topicName": topic_name,
            "command": command
        }
        
        await self.websocket.send(json.dumps(message))
        return True
        
    async def run_interactive_session(self):
        """Run interactive session"""
        if not await self.connect():
            return
            
        print("\nProgram-1 Interactive Client")
        print("Commands:")
        print("  создать топик <topic-name> - Create a new topic")
        print("  стоп - Stop current topic")
        print("  <command> - Send command to current topic")
        print("  quit - Exit")
        print()
        
        user_id = "demo_user_123"
        
        while True:
            try:
                user_input = input(f"[{self.current_topic or 'no-topic'}]> ").strip()
                
                if not user_input:
                    continue
                    
                if user_input.lower() == 'quit':
                    break
                    
                if user_input.startswith('создать топик '):
                    topic_name = user_input[14:].strip()
                    if topic_name:
                        await self.create_topic(topic_name, user_id)
                    else:
                        print("Please specify topic name")
                        
                elif user_input == 'стоп':
                    await self.stop_topic()
                    
                else:
                    # Send as command to current topic
                    if self.current_topic:
                        await self.send_command(user_input)
                    else:
                        print("No active topic. Create a topic first.")
                        
                # Small delay to allow responses to be processed
                await asyncio.sleep(0.1)
                
            except KeyboardInterrupt:
                print("\nExiting...")
                break
            except EOFError:
                break
                
        # Cleanup
        if self.current_topic:
            await self.stop_topic()
            await asyncio.sleep(0.5)  # Allow cleanup to complete
            
        if self.websocket:
            await self.websocket.close()


async def run_demo_scenario():
    """Run automated demo scenario"""
    print("Running Demo Scenario...")
    print("=" * 40)
    
    client = Program1Client()
    if not await client.connect():
        return
        
    # Demo scenario following the use cases
    user_id = "demo_user_123"
    topic_name = "demo-topic"
    
    print(f"\n1. Creating topic '{topic_name}'...")
    await client.create_topic(topic_name, user_id)
    await asyncio.sleep(2)
    
    print(f"\n2. Sending commands to topic...")
    commands = ["echo hello", "pwd", "ls -la", "date", "whoami"]
    
    for cmd in commands:
        print(f"   Sending: {cmd}")
        await client.send_command(cmd)
        await asyncio.sleep(1.5)
        
    print(f"\n3. Stopping topic '{topic_name}'...")
    await client.stop_topic()
    await asyncio.sleep(1)
    
    print("\nDemo completed!")
    await client.websocket.close()


async def main():
    """Main entry point"""
    if len(sys.argv) > 1 and sys.argv[1] == 'demo':
        await run_demo_scenario()
    else:
        client = Program1Client()
        await client.run_interactive_session()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExiting...")