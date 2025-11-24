.PHONY: help build up down test clean logs client demo

# Default target
help:
	@echo "Available targets:"
	@echo "  build    - Build Docker containers"
	@echo "  up       - Start the system with default timeouts"
	@echo "  up-dev   - Start with development config (30min WebSocket timeout)"
	@echo "  up-prod  - Start with production config (5min WebSocket timeout)"
	@echo "  down     - Stop the system"
	@echo "  test     - Run all tests"
	@echo "  clean    - Clean up Docker containers and volumes"
	@echo "  logs     - Show logs from both servers"
	@echo "  client   - Run interactive client"
	@echo "  demo     - Run demo scenario"

# Build Docker containers
build:
	docker compose build

# Start the system
up: build
	docker compose up -d
	@echo "System started. Servers available at:"
	@echo "  Server-1 HTTP: http://localhost:8004"
	@echo "  Server-2 WebSocket (clients): ws://localhost:8082"
	@echo "  Server-2 WebSocket (server-1): ws://localhost:8002"

# Start with development configuration (extended timeouts)
up-dev: build
	docker compose --env-file .env.development up -d
	@echo "Development system started with extended timeouts (30min idle)"
	@echo "  Server-1 HTTP: http://localhost:8004"
	@echo "  Server-2 WebSocket (clients): ws://localhost:8082"

# Start with production configuration
up-prod: build
	docker compose --env-file .env.production up -d
	@echo "Production system started with conservative timeouts (5min idle)"

# Stop the system
down:
	docker compose down

# Run tests
test:
	@echo "Installing test dependencies..."
	pip3 install -r tests/requirements.txt
	@echo "Running tests..."
	cd tests && python3 run_tests.py

# Clean up everything
clean: down
	docker compose down -v
	docker system prune -f
	@echo "Cleanup complete"

# Show logs
logs:
	docker compose logs -f

# Show logs for specific service
logs-server1:
	docker compose logs -f server1

logs-server2:
	docker compose logs -f server2

# Run interactive client (requires system to be running)
client:
	@echo "Starting interactive client..."
	@echo "Make sure the system is running with 'make up'"
	python3 client_example.py

# Run demo scenario
demo:
	@echo "Running demo scenario..."
	@echo "Make sure the system is running with 'make up'"
	python3 client_example.py demo

# Development targets
dev-server1:
	cd server1 && pip3 install -r requirements.txt && python3 tmux_manager.py

dev-server2:
	cd server2 && pip3 install -r requirements.txt && python3 websocket_server.py

# Check system status
status:
	@echo "Checking system status..."
	@curl -s http://localhost:8001/sessions -X POST -H "Content-Type: application/json" -d '{"user_id":"health_check"}' || echo "Server-1 not responding"
	@echo "Docker containers:"
	@docker compose ps