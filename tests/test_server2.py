#!/usr/bin/env python3

import asyncio
import json
import os
import sys
import unittest
import tempfile
import shutil
from unittest.mock import patch, MagicMock, AsyncMock
import websockets
import aiofiles

# Add parent directory to path to import server modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'server2'))
from websocket_server import WebSocketRouter, Program2Interface

class TestProgram2Interface(unittest.TestCase):
    def setUp(self):
        self.mock_router = MagicMock()
        self.mock_router.request_session_creation = AsyncMock()
        self.mock_router.request_session_destruction = AsyncMock()
        self.mock_router.send_command_to_session = AsyncMock()
        
        self.program2 = Program2Interface(self.mock_router)
        self.test_dir = tempfile.mkdtemp()
        
        # Patch the data directory
        self.data_dir_patcher = patch('websocket_server.os.makedirs')
        self.mock_makedirs = self.data_dir_patcher.start()
        
    def tearDown(self):
        self.data_dir_patcher.stop()
        shutil.rmtree(self.test_dir, ignore_errors=True)
        
    async def test_create_topic_success(self):
        """Test successful topic creation"""
        self.mock_router.request_session_creation.return_value = "session_123"
        
        with patch('websocket_server.os.makedirs'), \
             patch.object(self.program2, 'log_to_topic') as mock_log:
            
            result = await self.program2.create_topic("test_topic", "user_123")
            
            self.assertTrue(result)
            self.assertIn("test_topic", self.program2.topics)
            self.assertEqual(self.program2.topics["test_topic"], "session_123")
            
            # Verify session creation was requested
            self.mock_router.request_session_creation.assert_called_once_with("user_123")
            
            # Verify logging
            mock_log.assert_called_once_with("test_topic", "session opened - session_123")
            
    async def test_create_topic_session_failure(self):
        """Test topic creation when session creation fails"""
        self.mock_router.request_session_creation.return_value = None
        
        with patch('websocket_server.os.makedirs'):
            result = await self.program2.create_topic("test_topic", "user_123")
            
            self.assertFalse(result)
            self.assertNotIn("test_topic", self.program2.topics)
            
    async def test_stop_topic_success(self):
        """Test successful topic stopping"""
        # Setup existing topic
        self.program2.topics["test_topic"] = "session_123"
        
        with patch.object(self.program2, 'log_to_topic') as mock_log:
            result = await self.program2.stop_topic("test_topic")
            
            self.assertTrue(result)
            self.assertNotIn("test_topic", self.program2.topics)
            
            # Verify session destruction was requested
            self.mock_router.request_session_destruction.assert_called_once_with("session_123")
            
            # Verify logging
            mock_log.assert_called_once_with("test_topic", "стоп")
            
    async def test_stop_topic_not_found(self):
        """Test stopping non-existent topic"""
        result = await self.program2.stop_topic("nonexistent_topic")
        self.assertFalse(result)
        
    async def test_send_command_to_topic(self):
        """Test sending command to topic"""
        # Setup existing topic
        self.program2.topics["test_topic"] = "session_123"
        
        with patch.object(self.program2, 'log_to_topic') as mock_log:
            result = await self.program2.send_command_to_topic("test_topic", "ls -la")
            
            self.assertTrue(result)
            
            # Verify command was sent to session
            self.mock_router.send_command_to_session.assert_called_once_with("session_123", "ls -la")
            
            # Verify logging
            mock_log.assert_called_once_with("test_topic", "COMMAND: ls -la")
            
    async def test_handle_session_output(self):
        """Test handling session output"""
        # Setup existing topic
        self.program2.topics["test_topic"] = "session_123"
        
        with patch.object(self.program2, 'log_to_topic') as mock_log:
            await self.program2.handle_session_output("session_123", "command output")
            
            # Verify logging
            mock_log.assert_called_once_with("test_topic", "OUTPUT: command output")
            
    async def test_handle_session_output_unknown_session(self):
        """Test handling output from unknown session"""
        with patch.object(self.program2, 'log_to_topic') as mock_log:
            await self.program2.handle_session_output("unknown_session", "output")
            
            # Should not log anything for unknown sessions
            mock_log.assert_not_called()
            
    async def test_log_to_topic(self):
        """Test logging to topic file"""
        with patch('aiofiles.open', create=True) as mock_open:
            mock_file = AsyncMock()
            mock_open.return_value.__aenter__.return_value = mock_file
            
            await self.program2.log_to_topic("test_topic", "test message")
            
            # Verify file was opened and written to
            mock_open.assert_called_once_with("/data/topics/test_topic/test_topic.log", 'a')
            mock_file.write.assert_called_once()
            
            # Check that timestamp and message are in the written content
            written_content = mock_file.write.call_args[0][0]
            self.assertIn("test message", written_content)
            self.assertIn(" - ", written_content)  # Timestamp separator


class TestWebSocketRouter(unittest.TestCase):
    def setUp(self):
        self.router = WebSocketRouter()
        
    async def test_handle_server1_message_stdout(self):
        """Test handling stdout message from server-1"""
        mock_program2 = AsyncMock()
        self.router.set_program2_interface(mock_program2)
        
        message = json.dumps({
            "type": "stdout",
            "sessionId": "session_123",
            "data": "test output",
            "timestamp": "2025-11-24T10:30:00Z"
        })
        
        await self.router.handle_server1_message(message)
        
        # Verify output was handled
        mock_program2.handle_session_output.assert_called_once_with("session_123", "test output")
        
    async def test_handle_server1_message_invalid_json(self):
        """Test handling invalid JSON from server-1"""
        # Should not raise exception
        await self.router.handle_server1_message("invalid json")
        
    async def test_handle_client_message_create_topic(self):
        """Test handling create topic message from client"""
        mock_websocket = AsyncMock()
        mock_program2 = AsyncMock()
        mock_program2.create_topic.return_value = True
        self.router.set_program2_interface(mock_program2)
        
        message = json.dumps({
            "type": "create_topic",
            "topicName": "test_topic",
            "userId": "user_123"
        })
        
        await self.router.handle_client_message(mock_websocket, message)
        
        # Verify topic creation was called
        mock_program2.create_topic.assert_called_once_with("test_topic", "user_123")
        
        # Verify response was sent
        mock_websocket.send.assert_called_once()
        sent_message = json.loads(mock_websocket.send.call_args[0][0])
        self.assertEqual(sent_message["type"], "topic_created")
        self.assertEqual(sent_message["topicName"], "test_topic")
        self.assertTrue(sent_message["success"])
        
    async def test_handle_client_message_stop_topic(self):
        """Test handling stop topic message from client"""
        mock_websocket = AsyncMock()
        mock_program2 = AsyncMock()
        mock_program2.stop_topic.return_value = True
        self.router.set_program2_interface(mock_program2)
        
        message = json.dumps({
            "type": "stop_topic",
            "topicName": "test_topic"
        })
        
        await self.router.handle_client_message(mock_websocket, message)
        
        # Verify topic stopping was called
        mock_program2.stop_topic.assert_called_once_with("test_topic")
        
        # Verify response was sent
        mock_websocket.send.assert_called_once()
        sent_message = json.loads(mock_websocket.send.call_args[0][0])
        self.assertEqual(sent_message["type"], "topic_stopped")
        
    async def test_handle_client_message_send_command(self):
        """Test handling send command message from client"""
        mock_websocket = AsyncMock()
        mock_program2 = AsyncMock()
        mock_program2.send_command_to_topic.return_value = True
        self.router.set_program2_interface(mock_program2)
        
        message = json.dumps({
            "type": "send_command",
            "topicName": "test_topic",
            "command": "ls -la"
        })
        
        await self.router.handle_client_message(mock_websocket, message)
        
        # Verify command was sent
        mock_program2.send_command_to_topic.assert_called_once_with("test_topic", "ls -la")
        
        # Verify response was sent
        mock_websocket.send.assert_called_once()
        sent_message = json.loads(mock_websocket.send.call_args[0][0])
        self.assertEqual(sent_message["type"], "command_sent")
        self.assertEqual(sent_message["command"], "ls -la")
        
    async def test_request_session_creation_success(self):
        """Test successful session creation request"""
        with patch('aiohttp.ClientSession') as mock_session_class:
            mock_session = AsyncMock()
            mock_response = AsyncMock()
            mock_response.status = 201
            mock_response.json.return_value = {"session_id": "session_123"}
            
            mock_session.__aenter__.return_value = mock_session
            mock_session.post.return_value.__aenter__.return_value = mock_response
            mock_session_class.return_value = mock_session
            
            result = await self.router.request_session_creation("user_123")
            
            self.assertEqual(result, "session_123")
            mock_session.post.assert_called_once_with(
                'http://server1:8001/sessions',
                json={'user_id': 'user_123'}
            )
            
    async def test_request_session_creation_failure(self):
        """Test failed session creation request"""
        with patch('aiohttp.ClientSession') as mock_session_class:
            mock_session = AsyncMock()
            mock_response = AsyncMock()
            mock_response.status = 422
            
            mock_session.__aenter__.return_value = mock_session
            mock_session.post.return_value.__aenter__.return_value = mock_response
            mock_session_class.return_value = mock_session
            
            result = await self.router.request_session_creation("user_123")
            
            self.assertIsNone(result)
            
    async def test_send_command_to_session(self):
        """Test sending command to session"""
        mock_websocket = AsyncMock()
        self.router.server1_connection = mock_websocket
        
        await self.router.send_command_to_session("session_123", "test command")
        
        # Verify message was sent
        mock_websocket.send.assert_called_once()
        sent_message = json.loads(mock_websocket.send.call_args[0][0])
        self.assertEqual(sent_message["type"], "command")
        self.assertEqual(sent_message["sessionId"], "session_123")
        self.assertEqual(sent_message["data"], "test command")
        
    async def test_send_command_to_session_no_connection(self):
        """Test sending command when no server-1 connection"""
        self.router.server1_connection = None
        
        # Should not raise exception
        await self.router.send_command_to_session("session_123", "test command")


class TestIntegrationWorkflow(unittest.TestCase):
    """Integration test for complete workflow"""
    
    async def test_complete_topic_workflow(self):
        """Test complete workflow: create topic, send command, get output, stop topic"""
        
        # Setup
        router = WebSocketRouter()
        program2 = Program2Interface(router)
        router.set_program2_interface(program2)
        
        # Mock dependencies
        with patch('websocket_server.os.makedirs'), \
             patch.object(program2, 'log_to_topic') as mock_log, \
             patch.object(router, 'request_session_creation', return_value="session_123") as mock_create, \
             patch.object(router, 'send_command_to_session') as mock_send_cmd, \
             patch.object(router, 'request_session_destruction') as mock_destroy:
            
            # 1. Create topic
            result = await program2.create_topic("integration_topic", "user_123")
            self.assertTrue(result)
            self.assertIn("integration_topic", program2.topics)
            
            # 2. Send command
            result = await program2.send_command_to_topic("integration_topic", "echo hello")
            self.assertTrue(result)
            mock_send_cmd.assert_called_with("session_123", "echo hello")
            
            # 3. Handle output
            await program2.handle_session_output("session_123", "hello")
            
            # 4. Stop topic
            result = await program2.stop_topic("integration_topic")
            self.assertTrue(result)
            self.assertNotIn("integration_topic", program2.topics)
            mock_destroy.assert_called_with("session_123")
            
            # Verify all logging calls
            expected_logs = [
                ("integration_topic", "session opened - session_123"),
                ("integration_topic", "COMMAND: echo hello"),
                ("integration_topic", "OUTPUT: hello"),
                ("integration_topic", "стоп")
            ]
            
            self.assertEqual(mock_log.call_count, len(expected_logs))
            for i, (expected_topic, expected_message) in enumerate(expected_logs):
                call_args = mock_log.call_args_list[i][0]
                self.assertEqual(call_args[0], expected_topic)
                self.assertEqual(call_args[1], expected_message)


if __name__ == '__main__':
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add test cases
    suite.addTests(loader.loadTestsFromTestCase(TestProgram2Interface))
    suite.addTests(loader.loadTestsFromTestCase(TestWebSocketRouter))
    suite.addTests(loader.loadTestsFromTestCase(TestIntegrationWorkflow))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Exit with proper code
    sys.exit(0 if result.wasSuccessful() else 1)