import subprocess
import sys

print("Installing requirements...")
try:
    subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], check=True)
except subprocess.CalledProcessError as e:
    print(f"Failed to install requirements: {e}")
    sys.exit(1)

print("Installing Playwright browsers...")
try:
    subprocess.run([sys.executable, "-m", "playwright", "install"], check=True)
except subprocess.CalledProcessError as e:
    print(f"Failed to install Playwright browsers: {e}")
    print("You may need to run 'playwright install' manually.")

print("\nSetup complete! Run 'python main.py' to start MARK XXV.")

