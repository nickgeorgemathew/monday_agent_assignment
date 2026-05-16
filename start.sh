#!/bin/bash
set -e
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
    echo "✅ Environment loaded"
else
    echo "⚠️  No .env file. Copy .env.example to .env and fill in values."
    exit 1
fi
echo "🚀 Starting FastAPI on port 8000..."
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload &
sleep 2
echo "🎨 Starting Streamlit on port 8501..."
streamlit run frontend/app.py --server.port 8501 --server.address 0.0.0.0 &
echo ""
echo "✅ Running:"
echo "   Frontend: http://localhost:8501"
echo "   Backend:  http://localhost:8000"
echo "   API docs: http://localhost:8000/docs"
wait
