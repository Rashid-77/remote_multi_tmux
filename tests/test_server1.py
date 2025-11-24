#!/usr/bin/env python3

import asyncio
import json
import os
import sys
import unittest
import tempfile
import shutil
from unittest.mock import patch, MagicMock, AsyncMock
import aiohttp
import websockets
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

# Add parent directory to path to import server modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'server1'))
from tmux_manager import TmuxSessionManager, TmuxHTTPServer

class TestTmuxSessionManager(unittest.TestCase):
    def setUp(self):
        self.manager = TmuxSessionManager("test_session")
        self.temp_dir = tempfile.mkdtemp()
        
    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        
    @patch('subprocess.run')
    async def test_create_session_success(self, mock_subprocess):
        """Test successful session creation"""
        mock_subprocess.return_value = MagicMock(returncode=0)
        
        with patch.dict(os.environ, {'PATH': f"{os.path.dirname(__file__)}:{os.environ.get('PATH', '')}"}):
            user_id = "test_user_123"
            session_id = await self.manager.create_session(user_id)
            
            self.assertIsNotNone(session_id)
            self.assertIn(session_id, self.manager.sessions)
            
            # Verify tmux commands were called
            self.assertTrue(mock_subprocess.called)
            
    @patch('subprocess.run')
    async def test_create_session_failure(self, mock_subprocess):
        """Test session creation failure"""
        from subprocess import CalledProcessError
        mock_subprocess.side_effect = CalledProcessError(1, 'tmux')
        
        user_id = "test_user_123"
        
        with self.assertRaises(Exception):
            await self.manager.create_session(user_id)
            
    @patch('subprocess.run')
    async def test_destroy_session_success(self, mock_subprocess):
        """Test successful session destruction"""
        mock_subprocess.return_value = MagicMock(returncode=0)
        
        # First create a session
        session_id = "test_session_id"
        self.manager.sessions[session_id] = "test_window"
        
        result = await self.manager.destroy_session(session_id)
        
        self.assertTrue(result)
        self.assertNotIn(session_id, self.manager.sessions)
        
    async def test_destroy_nonexistent_session(self):
        """Test destroying a non-existent session"""
        result = await self.manager.destroy_session("nonexistent_id")
        self.assertFalse(result)
        
    @patch('subprocess.run')
    async def test_send_command_to_session(self, mock_subprocess):
        """Test sending command to session"""
        mock_subprocess.return_value = MagicMock(returncode=0)
        
        session_id = "test_session_id"
        window_name = "test_window"
        self.manager.sessions[session_id] = window_name
        
        await self.manager.send_command_to_session(session_id, "echo test")
        
        # Verify tmux send-keys was called
        self.assertTrue(mock_subprocess.called)
        call_args = mock_subprocess.call_args[0][0]
        self.assertEqual(call_args[0], "tmux")
        self.assertEqual(call_args[1], "send-keys")
        
    async def test_handle_command(self):
        """Test handling WebSocket commands"""
        session_id = "test_session_id"
        self.manager.sessions[session_id] = "test_window"
        
        with patch.object(self.manager, 'send_command_to_session') as mock_send:
            # Test command handling
            await self.manager.handle_command({
                'type': 'command',
                'sessionId': session_id,
                'data': 'ls -la'
            })
            
            mock_send.assert_called_once_with(session_id, 'ls -la')
            
        with patch.object(self.manager, 'destroy_session') as mock_destroy:
            # Test session destroy handling
            await self.manager.handle_command({
                'type': 'session_destroy',
                'sessionId': session_id
            })
            
            mock_destroy.assert_called_once_with(session_id)


class TestTmuxHTTPServer(AioHTTPTestCase):
    async def get_application(self):
        """Create test application"""
        from aiohttp import web
        
        self.tmux_manager = TmuxSessionManager("test_session")
        self.http_server = TmuxHTTPServer(self.tmux_manager)
        
        app = web.Application()
        app.router.add_post('/sessions', self.http_server.create_session)
        app.router.add_delete('/sessions/{session_id}', self.http_server.delete_session)
        
        return app
        
    @unittest_run_loop
    async def test_create_session_endpoint(self):
        """Test the create session HTTP endpoint"""
        with patch.object(self.tmux_manager, 'create_session', return_value="test_session_123"):
            resp = await self.client.request(
                "POST", 
                "/sessions",
                json={"user_id": "test_user"}
            )
            
            self.assertEqual(resp.status, 201)
            data = await resp.json()
            
            self.assertIn('session_id', data)
            self.assertIn('created_at', data)
            self.assertIn('websocket_endpoint', data)
            self.assertEqual(data['session_id'], "test_session_123")
            
    @unittest_run_loop
    async def test_create_session_missing_user_id(self):
        """Test create session with missing user_id"""
        resp = await self.client.request(
            "POST", 
            "/sessions",
            json={}
        )
        
        self.assertEqual(resp.status, 400)
        data = await resp.json()
        self.assertIn('error', data)
        
    @unittest_run_loop
    async def test_create_session_failure(self):
        """Test create session failure"""
        with patch.object(self.tmux_manager, 'create_session', side_effect=Exception("Creation failed")):
            resp = await self.client.request(
                "POST", 
                "/sessions",
                json={"user_id": "test_user"}
            )
            
            self.assertEqual(resp.status, 422)
            
    @unittest_run_loop
    async def test_delete_session_success(self):
        """Test successful session deletion"""
        with patch.object(self.tmux_manager, 'destroy_session', return_value=True):
            resp = await self.client.request(
                "DELETE", 
                "/sessions/test_session_123"
            )
            
            self.assertEqual(resp.status, 204)
            
    @unittest_run_loop
    async def test_delete_session_not_found(self):
        """Test deleting non-existent session"""
        with patch.object(self.tmux_manager, 'destroy_session', return_value=False):
            resp = await self.client.request(
                "DELETE", 
                "/sessions/nonexistent_session"
            )
            
            self.assertEqual(resp.status, 404)


class TestTmuxIntegration(unittest.TestCase):
    """Integration tests using the tmux mock"""
    
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        # Set PATH to include our tmux mock
        self.original_path = os.environ.get('PATH', '')
        os.environ['PATH'] = f"{os.path.dirname(__file__)}:{self.original_path}"
        
        # Make tmux mock executable
        tmux_mock_path = os.path.join(os.path.dirname(__file__), 'tmux')
        if not os.path.exists(tmux_mock_path):
            # Create symlink to tmux_mock.py
            tmux_mock_script = os.path.join(os.path.dirname(__file__), 'tmux_mock.py')
            with open(tmux_mock_path, 'w') as f:
                f.write(f'#!/bin/bash\npython3 {tmux_mock_script} "$@"\n')
            os.chmod(tmux_mock_path, 0o755)
        
    def tearDown(self):
        os.environ['PATH'] = self.original_path
        shutil.rmtree(self.test_dir, ignore_errors=True)
        
        # Clean up tmux mock
        tmux_mock_path = os.path.join(os.path.dirname(__file__), 'tmux')
        if os.path.exists(tmux_mock_path):
            os.remove(tmux_mock_path)
            
    async def test_full_session_lifecycle(self):
        """Test complete session lifecycle with tmux mock"""
        manager = TmuxSessionManager("integration_test")
        
        # Start the manager (this will try to create tmux session)
        with patch('websockets.connect'):  # Mock websocket connection
            await manager.start()
        
        # Create a session
        session_id = await manager.create_session("integration_user")
        self.assertIsNotNone(session_id)
        self.assertIn(session_id, manager.sessions)
        
        # Send a command
        await manager.send_command_to_session(session_id, 'echo "integration test"')
        
        # Allow some time for command processing
        await asyncio.sleep(0.1)
        
        # Destroy session
        result = await manager.destroy_session(session_id)
        self.assertTrue(result)
        self.assertNotIn(session_id, manager.sessions)


if __name__ == '__main__':
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add test cases
    suite.addTests(loader.loadTestsFromTestCase(TestTmuxSessionManager))
    suite.addTests(loader.loadTestsFromTestCase(TestTmuxHTTPServer))
    suite.addTests(loader.loadTestsFromTestCase(TestTmuxIntegration))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Exit with proper code
    sys.exit(0 if result.wasSuccessful() else 1)