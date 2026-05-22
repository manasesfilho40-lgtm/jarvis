import sys
import time
import builtins
import subprocess
from actions.open_app import open_app

def print(*args, **kwargs):
    if sys.stdout is None:
        return
    try:
        builtins.print(*args, **kwargs)
    except Exception:
        pass

def main():
    print("[Startup] Running automatic actions...")
    
    # 1. Open Claude Desktop App
    open_app({"app_name": "Claude"})
    time.sleep(2.5)
    
    # 2. Open Spotify and play Highway to Hell
    open_app({
        "app_name": "Spotify", 
        "query": "highway to hell acdc"
    })
    
    print("[Startup] Automatic actions completed.")

if __name__ == "__main__":
    main()
