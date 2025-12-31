#!/bin/bash
set -e  # Exit on any error

echo "================================================"
echo "🚀 Starting Build Process"
echo "================================================"

# Build Frontend
echo ""
echo "📦 Step 1: Building Frontend..."
cd frontend
echo "Current directory: $(pwd)"
echo "Installing dependencies..."
npm ci
echo "Running build..."
npm run build
echo "✅ Frontend build complete!"
echo "Build output contents:"
ls -lah dist/
cd ..

# Install Backend Dependencies
echo ""
echo "📦 Step 2: Installing Backend Dependencies..."
pip3 install -r backend/requirements.txt
echo "✅ Backend dependencies installed!"

echo ""
echo "================================================"
echo "✅ BUILD COMPLETE"
echo "================================================"
echo "Frontend build location: $(pwd)/frontend/dist"
echo "Contents:"
ls -lah frontend/dist/ || echo "⚠️ Frontend dist not found!"
