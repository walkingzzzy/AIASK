import uvicorn
import sys

if __name__ == "__main__":
    print("Starting Desktop API in debug mode...")
    print(f"Python: {sys.version}")
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8001,
        log_level="debug",
        reload=False
    )
