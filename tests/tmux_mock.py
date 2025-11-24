#!/usr/bin/env python3

import os
import sys
import time
import random
import signal
from pathlib import Path

class TmuxMock:
    """Mock tmux implementation for testing that generates dynamic responses"""
    
    def __init__(self):
        self.sessions = {}
        self.windows = {}
        self.window_outputs = {}
        self.command_responses = {
            'echo "старт"': 'старт',
            'ls': 'file1.txt  file2.txt  directory1/',
            'pwd': '/tmp/test',
            'date': lambda: time.strftime('%a %b %d %H:%M:%S %Z %Y'),
            'whoami': 'testuser',
            'ps': 'PID TTY          TIME CMD\n1234 pts/0    00:00:01 bash',
            'cat /etc/hostname': 'test-container',
            'df -h': 'Filesystem      Size  Used Avail Use% Mounted on\n/dev/disk1s1   465Gi  123Gi  340Gi  27% /',
        }
        
    def run_command(self, args):
        """Main entry point for tmux mock commands"""
        if len(args) < 2:
            return "tmux: need command"
            
        command = args[1]
        
        if command == "has-session":
            return self.has_session(args[2:])
        elif command == "new-session":
            return self.new_session(args[2:])
        elif command == "new-window":
            return self.new_window(args[2:])
        elif command == "send-keys":
            return self.send_keys(args[2:])
        elif command == "capture-pane":
            return self.capture_pane(args[2:])
        elif command == "kill-window":
            return self.kill_window(args[2:])
        else:
            return f"tmux: unknown command: {command}"
            
    def has_session(self, args):
        """Check if session exists"""
        if "-t" in args:
            session_name = args[args.index("-t") + 1]
            if session_name not in self.sessions:
                sys.exit(1)  # Session doesn't exist
        return ""
        
    def new_session(self, args):
        """Create new tmux session"""
        session_name = "default"
        if "-s" in args:
            session_name = args[args.index("-s") + 1]
            
        self.sessions[session_name] = {
            'windows': [],
            'created': time.time()
        }
        return ""
        
    def new_window(self, args):
        """Create new tmux window"""
        session_name = "default"
        window_name = f"window-{len(self.windows)}"
        
        if "-t" in args:
            session_name = args[args.index("-t") + 1]
        if "-n" in args:
            window_name = args[args.index("-n") + 1]
            
        if session_name not in self.sessions:
            sys.exit(1)  # Session doesn't exist
            
        window_id = f"{session_name}:{window_name}"
        self.windows[window_id] = {
            'session': session_name,
            'name': window_name,
            'created': time.time(),
            'commands': [],
            'output_lines': []
        }
        
        self.sessions[session_name]['windows'].append(window_name)
        return ""
        
    def send_keys(self, args):
        """Send keys to tmux window"""
        if "-t" not in args:
            return "tmux: no target specified"
            
        target = args[args.index("-t") + 1]
        command_parts = args[args.index("-t") + 2:]
        
        # Remove "Enter" if present
        if command_parts and command_parts[-1] == "Enter":
            command_parts = command_parts[:-1]
            
        command = " ".join(command_parts)
        
        if target not in self.windows:
            return f"tmux: can't find window {target}"
            
        # Record the command
        self.windows[target]['commands'].append(command)
        
        # Generate response based on command
        response = self.generate_command_response(command)
        if response:
            self.windows[target]['output_lines'].extend(response.split('\n'))
            
        return ""
        
    def capture_pane(self, args):
        """Capture pane content"""
        if "-t" not in args:
            return "tmux: no target specified"
            
        target = args[args.index("-t") + 1]
        
        if target not in self.windows:
            return ""
            
        # Return accumulated output
        output_lines = self.windows[target]['output_lines']
        if not output_lines:
            return ""
            
        return "\n".join(output_lines)
        
    def kill_window(self, args):
        """Kill tmux window"""
        if "-t" not in args:
            return "tmux: no target specified"
            
        target = args[args.index("-t") + 1]
        
        if target in self.windows:
            session_name = self.windows[target]['session']
            window_name = self.windows[target]['name']
            
            # Remove from session
            if session_name in self.sessions:
                if window_name in self.sessions[session_name]['windows']:
                    self.sessions[session_name]['windows'].remove(window_name)
                    
            # Remove window
            del self.windows[target]
            
        return ""
        
    def generate_command_response(self, command):
        """Generate realistic responses to commands"""
        command = command.strip()
        
        # Direct matches
        if command in self.command_responses:
            response = self.command_responses[command]
            if callable(response):
                return response()
            return response
            
        # Pattern matches
        if command.startswith('echo'):
            # Echo back the content
            content = command[4:].strip().strip('"').strip("'")
            return content
            
        elif command.startswith('ls'):
            # Generate random file listing
            files = ['README.md', 'config.json', 'data.txt', 'script.py', 'test_dir/']
            return '  '.join(random.sample(files, random.randint(2, len(files))))
            
        elif command.startswith('cat'):
            # Generate file content
            filename = command.split()[-1] if len(command.split()) > 1 else 'file'
            return f"Content of {filename}:\nLine 1 of content\nLine 2 of content\nEnd of file"
            
        elif command.startswith('grep'):
            return "match found in line 42: example content"
            
        elif command == 'uptime':
            return f"up {random.randint(1, 100)} days, {random.randint(1, 24)} hours"
            
        elif command in ['clear', 'cls']:
            # Clear doesn't produce output
            return ""
            
        elif command.startswith('mkdir'):
            dirname = command.split()[-1] if len(command.split()) > 1 else 'newdir'
            return f"Directory '{dirname}' created"
            
        elif command.startswith('rm'):
            return "Files removed"
            
        elif command.startswith('cp'):
            return "Files copied"
            
        elif command.startswith('mv'):
            return "Files moved"
            
        elif command.startswith('find'):
            return "./file1.txt\n./subdir/file2.txt\n./another/file3.log"
            
        elif command == 'help' or command == '--help':
            return "Available commands: ls, pwd, date, echo, cat, etc."
            
        else:
            # Generic response for unknown commands
            responses = [
                f"Command '{command}' executed successfully",
                f"Output from '{command}':\nResult line 1\nResult line 2",
                f"Processing '{command}'...\nDone.",
                f"'{command}' completed with exit code 0",
                f"Running '{command}'...\nOperation successful"
            ]
            return random.choice(responses)


def main():
    """Main entry point for tmux mock"""
    mock = TmuxMock()
    
    # Handle signal for graceful shutdown
    def signal_handler(signum, frame):
        sys.exit(0)
        
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        result = mock.run_command(sys.argv)
        if result:
            print(result, end='')
    except SystemExit:
        raise
    except Exception as e:
        print(f"tmux: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()