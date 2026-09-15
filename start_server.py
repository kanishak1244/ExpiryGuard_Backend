import os
import sys
import uvicorn

if __name__ == "__main__":
    port_str = os.environ.get("PORT", "8000").strip()
    try:
        port = int(port_str)
    except ValueError:
        port = 8000
    
    print(f"[DawaiFlow Server Launcher] Starting Uvicorn on 0.0.0.0:{port}...")
    sys.stdout.flush()
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=port,
        workers=1,
        proxy_headers=True,
        forwarded_allow_ips="*"
    )
