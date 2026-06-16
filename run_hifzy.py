import os
import sys
import subprocess

def run_app():
    # Get the directory where this script is located
    base_dir = os.path.dirname(os.path.abspath(__file__))
    # Construct the path to the main entry point
    main_script = os.path.join(base_dir, "main.py")

    # Launch main.py using the current Python executable
    subprocess.run([sys.executable, main_script])

if __name__ == "__main__":
    run_app()