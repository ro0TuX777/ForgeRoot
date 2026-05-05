#!/bin/sh

# Function to cleanup processes on exit
cleanup() {
    echo "Cleaning up..."
    kill -TERM $VITE_PID 2>/dev/null
    nginx -s quit
    exit 0
}

# Function to wait for service to be ready
wait_for_service() {
    local host=$1
    local port=$2
    local service=$3
    
    echo "Waiting for $service to be ready..."
    while ! nc -z $host $port; do
        sleep 1
    done
    echo "$service is ready!"
}

# Trap SIGTERM and SIGINT
trap cleanup TERM INT

# Create required nginx directories
mkdir -p /run/nginx

# Start Vite dev server in background
echo "Starting Vite dev server..."
npm run dev -- --host 0.0.0.0 --port 3001 &
VITE_PID=$!

# Wait for Vite to be ready
wait_for_service localhost 3001 "Vite dev server"

# Start nginx after Vite is ready
echo "Starting nginx..."
nginx

# Keep the script running
while true; do
    if ! kill -0 $VITE_PID 2>/dev/null; then
        echo "Vite dev server exited. Shutting down..."
        cleanup
    fi
    sleep 1
done
