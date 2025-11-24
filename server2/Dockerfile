FROM ubuntu:22.04

# Install Python and system dependencies
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy application code
COPY websocket_server.py .

# Create data directory
RUN mkdir -p /data/topics

# Expose WebSocket ports
EXPOSE 8000 8080

CMD ["python3", "websocket_server.py"]