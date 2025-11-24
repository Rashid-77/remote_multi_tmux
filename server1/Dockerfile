FROM ubuntu:22.04

# Install tmux and other system dependencies
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    tmux \
    bash \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy application code
COPY tmux_manager.py .

# Create directories for sessions
RUN mkdir -p /tmp/sessions

# Expose HTTP port
EXPOSE 8001

CMD ["python3", "tmux_manager.py"]