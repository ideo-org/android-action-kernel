
"""
Federal Digital Rupee Automation Agent

Goal: Open Federal Digital Rupee app and simplify the payment/send money process.
"""

import sys
from kernel import run_agent, Config

# Hardcoded package name for Federal Digital Rupee (assumed)
# Real users might need to adjust this if it differs
APP_PACKAGE = "com.federalbank.digitalrupee"
APP_NAME = "Digital Rupee"

def main():
    print(f"🤖 Federal Digital Rupee Agent Initialization...")
    
    # Custom goal designed for this specific app workflow
    # We prime the agent to launch the app first
    goal = (
        f"Open the {APP_NAME} app (package: {APP_PACKAGE}). "
        "Navigate to the 'Send Money' or 'Pay' section. "
        "If a PIN is required, ask the user or wait for manual entry. "
        "If I need to scan a QR code, find the 'Scan' button. "
        "My ultimate goal is to reach the payment screen."
    )
    
    # We can override config defaults here if needed
    # Config.MAX_STEPS = 20 

    print(f"🎯 Objective: {goal}")
    print("Press Ctrl+C to stop.")
    
    try:
        run_agent(goal)
    except KeyboardInterrupt:
        print("\n🛑 Agent stopped by user.")

if __name__ == "__main__":
    main()
