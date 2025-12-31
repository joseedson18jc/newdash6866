# Makefile for Financial Control App

# Use this Makefile to start development services consistently.
# It avoids accidental multiple uvicorn processes.

.PHONY: dev-backend dev-frontend

# Start the FastAPI backend on port 8000 using the wrapper script.
# Ensure the script is executable: chmod +x run_backend.sh
dev-backend:
	@echo "🚀 Starting backend via run_backend.sh"
	./run_backend.sh

# Optional: start the Vite frontend (if you prefer a single command).
# This runs npm install then npm run dev.
dev-frontend:
	@echo "🚀 Starting frontend"
	cd frontend && npm install && npm run dev
