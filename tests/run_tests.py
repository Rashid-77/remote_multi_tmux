#!/usr/bin/env python3

import sys
import os
import subprocess
import unittest

def run_all_tests():
    """Run all tests with proper setup"""
    
    # Ensure tmux mock is executable
    tmux_mock_path = os.path.join(os.path.dirname(__file__), 'tmux')
    if not os.path.exists(tmux_mock_path):
        tmux_mock_script = os.path.join(os.path.dirname(__file__), 'tmux_mock.py')
        with open(tmux_mock_path, 'w') as f:
            f.write(f'#!/bin/bash\npython3 {tmux_mock_script} "$@"\n')
        os.chmod(tmux_mock_path, 0o755)
    
    # Make tmux_mock.py executable too
    tmux_mock_script = os.path.join(os.path.dirname(__file__), 'tmux_mock.py')
    if os.path.exists(tmux_mock_script):
        os.chmod(tmux_mock_script, 0o755)
    
    print("Running Server-1 Tests...")
    print("=" * 50)
    
    # Run server1 tests
    try:
        result1 = subprocess.run([
            sys.executable, 
            os.path.join(os.path.dirname(__file__), 'test_server1.py')
        ], capture_output=False)
    except Exception as e:
        print(f"Error running server1 tests: {e}")
        result1 = type('Result', (), {'returncode': 1})()
    
    print("\nRunning Server-2 Tests...")
    print("=" * 50)
    
    # Run server2 tests
    try:
        result2 = subprocess.run([
            sys.executable, 
            os.path.join(os.path.dirname(__file__), 'test_server2.py')
        ], capture_output=False)
    except Exception as e:
        print(f"Error running server2 tests: {e}")
        result2 = type('Result', (), {'returncode': 1})()
    
    print("\n" + "=" * 50)
    print("Test Summary:")
    print(f"Server-1 tests: {'PASSED' if result1.returncode == 0 else 'FAILED'}")
    print(f"Server-2 tests: {'PASSED' if result2.returncode == 0 else 'FAILED'}")
    
    # Clean up
    if os.path.exists(tmux_mock_path):
        os.remove(tmux_mock_path)
    
    return result1.returncode == 0 and result2.returncode == 0

if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)