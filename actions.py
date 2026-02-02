"""
Action execution module for Android Action Kernel.
Handles all ADB commands for interacting with Android devices.
"""

import subprocess
import time
from typing import Dict, Any, List

from config import Config
from constants import (
    KEYCODE_ENTER,
    KEYCODE_HOME,
    KEYCODE_BACK,
    SWIPE_COORDS,
    SWIPE_DURATION_MS,
)


def run_adb_command(command: List[str]) -> str:
    """Executes a shell command via ADB."""
    result = subprocess.run(
        [Config.ADB_PATH] + command,
        capture_output=True,
        text=True
    )
    if result.stderr and "error" in result.stderr.lower():
        print(f"❌ ADB Error: {result.stderr.strip()}")
    return result.stdout.strip()


def execute_action(action: Dict[str, Any]) -> None:
    """Executes the action decided by the LLM."""
    act_type = action.get("action")

    if act_type == "tap":
        _execute_tap(action)
    elif act_type == "type":
        _execute_type(action)
    elif act_type == "enter":
        _execute_enter()
    elif act_type == "swipe":
        _execute_swipe(action)
    elif act_type == "home":
        _execute_home()
    elif act_type == "back":
        _execute_back()
    elif act_type == "wait":
        _execute_wait()
    elif act_type == "launch_app":
        _execute_launch_app(action)
    elif act_type == "done":
        _execute_done()
    else:
        print(f"⚠️ Unknown action: {act_type}")


def _execute_launch_app(action: Dict[str, Any]) -> None:
    """Launch an app by package name."""
    app_name = action.get("app_name", "")
    package_name = action.get("package_name")

    if not package_name:
        # Fallback to simple matching if no package name provided (mock implementation for robustness)
        # Real-world: Better to use exact package name
        print(f"⚠️ No package name provided for {app_name}, trying monkey launch...")
        run_adb_command(["shell", "monkey", "-p", app_name, "-c", "android.intent.category.LAUNCHER", "1"])
        return

    print(f"🚀 Launching App: {app_name} ({package_name})")
    # Using monkey is often easier than am start if we don't know the main activity
    run_adb_command(["shell", "monkey", "-p", package_name, "-c", "android.intent.category.LAUNCHER", "1"])



def _execute_tap(action: Dict[str, Any]) -> None:
    """Execute a tap action at specified coordinates."""
    x, y = action.get("coordinates", [0, 0])
    print(f"👉 Tapping: ({x}, {y})")
    run_adb_command(["shell", "input", "tap", str(x), str(y)])


def _execute_type(action: Dict[str, Any]) -> None:
    """Execute a type action to input text."""
    text = action.get("text", "")
    # ADB requires %s for spaces
    escaped_text = text.replace(" ", "%s")
    print(f"⌨️ Typing: {text}")
    run_adb_command(["shell", "input", "text", escaped_text])


def _execute_enter() -> None:
    """Press the Enter key."""
    print("⏎ Pressing Enter")
    run_adb_command(["shell", "input", "keyevent", KEYCODE_ENTER])


def _execute_swipe(action: Dict[str, Any]) -> None:
    """Execute a swipe action in the specified direction."""
    direction = action.get("direction", "up")
    coords = SWIPE_COORDS.get(direction, SWIPE_COORDS["up"])

    print(f"👆 Swiping {direction.capitalize()}")
    run_adb_command([
        "shell", "input", "swipe",
        str(coords[0]), str(coords[1]),
        str(coords[2]), str(coords[3]),
        SWIPE_DURATION_MS
    ])


def _execute_home() -> None:
    """Navigate to home screen."""
    print("🏠 Going Home")
    run_adb_command(["shell", "input", "keyevent", KEYCODE_HOME])


def _execute_back() -> None:
    """Navigate back."""
    print("🔙 Going Back")
    run_adb_command(["shell", "input", "keyevent", KEYCODE_BACK])


def _execute_wait() -> None:
    """Wait for UI to load."""
    print("⏳ Waiting...")
    time.sleep(2)


def _execute_done() -> None:
    """Mark task as complete and exit."""
    print("✅ Goal Achieved.")
    exit(0)
