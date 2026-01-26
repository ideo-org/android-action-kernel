import os
import time
import subprocess
import json
from typing import Dict, Any, List
from openai import OpenAI
from dotenv import load_dotenv
import sanitizer

# Load environment variables from .env file
load_dotenv()

# --- CONFIGURATION ---
ADB_PATH = "adb"  # Ensure adb is in your PATH
SCREEN_DUMP_PATH = "/sdcard/window_dump.xml"
LOCAL_DUMP_PATH = "window_dump.xml"

# LLM Provider: "groq" or "openai"
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "groq")

if LLM_PROVIDER == "groq":
    MODEL = "llama-3.3-70b-versatile"  # Fast and capable
    client = OpenAI(
        api_key=os.environ.get("GROQ_API_KEY"),
        base_url="https://api.groq.com/openai/v1"
    )
else:
    MODEL = "gpt-4o"
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

def run_adb_command(command: List[str]):
    """Executes a shell command via ADB."""
    result = subprocess.run([ADB_PATH] + command, capture_output=True, text=True)
    if result.stderr and "error" in result.stderr.lower():
        print(f"❌ ADB Error: {result.stderr.strip()}")
    return result.stdout.strip()

def get_screen_state() -> str:
    """Dumps the current UI XML and returns the sanitized JSON string."""
    # 1. Capture XML
    run_adb_command(["shell", "uiautomator", "dump", SCREEN_DUMP_PATH])
    
    # 2. Pull to local
    run_adb_command(["pull", SCREEN_DUMP_PATH, LOCAL_DUMP_PATH])
    
    # 3. Read & Sanitize
    if not os.path.exists(LOCAL_DUMP_PATH):
        return "Error: Could not capture screen."
        
    with open(LOCAL_DUMP_PATH, "r", encoding="utf-8") as f:
        xml_content = f.read()
        
    elements = sanitizer.get_interactive_elements(xml_content)
    return json.dumps(elements, indent=2)

def execute_action(action: Dict[str, Any]):
    """Executes the action decided by the LLM."""
    act_type = action.get("action")
    
    if act_type == "tap":
        x, y = action.get("coordinates")
        print(f"👉 Tapping: ({x}, {y})")
        run_adb_command(["shell", "input", "tap", str(x), str(y)])
        
    elif act_type == "type":
        text = action.get("text").replace(" ", "%s") # ADB requires %s for spaces
        print(f"⌨️ Typing: {action.get('text')}")
        run_adb_command(["shell", "input", "text", text])
        
    elif act_type == "home":
        print("🏠 Going Home")
        run_adb_command(["shell", "input", "keyevent", "KEYWORDS_HOME"])
        
    elif act_type == "back":
        print("🔙 Going Back")
        run_adb_command(["shell", "input", "keyevent", "KEYWORDS_BACK"])
        
    elif act_type == "wait":
        print("⏳ Waiting...")
        time.sleep(2)
        
    elif act_type == "done":
        print("✅ Goal Achieved.")
        exit(0)

def get_llm_decision(goal: str, screen_context: str, action_history: list) -> Dict[str, Any]:
    """Sends screen context to LLM and asks for the next move."""
    system_prompt = """
    You are an Android Driver Agent. Your job is to achieve the user's goal by navigating the UI.

    You will receive:
    1. The User's Goal.
    2. A list of interactive UI elements (JSON) with their (x,y) center coordinates.
    3. Your previous actions (so you don't repeat yourself).

    You must output ONLY a valid JSON object with your next action.

    Available Actions:
    - {"action": "tap", "coordinates": [x, y], "reason": "Why you are tapping"}
    - {"action": "type", "text": "Hello World", "reason": "Why you are typing"}
    - {"action": "home", "reason": "Go to home screen"}
    - {"action": "back", "reason": "Go back"}
    - {"action": "wait", "reason": "Wait for loading"}
    - {"action": "done", "reason": "Task complete"}

    IMPORTANT RULES:
    - If an element has "editable": true or "action": "type", use the "type" action to enter text.
    - After tapping on a text field, your NEXT action should be "type" to enter text.
    - Do NOT tap the same element repeatedly. If you already tapped it, try a different action.
    - If you see a search box or text input that needs text, use "type" directly.

    Example - Tapping a button:
    {"action": "tap", "coordinates": [540, 1200], "reason": "Clicking the 'Connect' button"}

    Example - Typing in a search box:
    {"action": "type", "text": "White House", "reason": "Entering search query in the search box"}
    """

    # Format action history
    history_str = ""
    if action_history:
        history_str = "\n\nPREVIOUS_ACTIONS:\n" + "\n".join(
            [f"Step {i+1}: {a['action']} - {a.get('reason', 'N/A')}" for i, a in enumerate(action_history)]
        )

    response = client.chat.completions.create(
        model=MODEL,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"GOAL: {goal}\n\nSCREEN_CONTEXT:\n{screen_context}{history_str}"}
        ]
    )

    return json.loads(response.choices[0].message.content)

def run_agent(goal: str, max_steps=10):
    print(f"🚀 Android Use Agent Started. Goal: {goal}")

    action_history = []

    for step in range(max_steps):
        print(f"\n--- Step {step + 1} ---")

        # 1. Perception
        print("👀 Scanning Screen...")
        screen_context = get_screen_state()

        # 2. Reasoning
        print("🧠 Thinking...")
        decision = get_llm_decision(goal, screen_context, action_history)
        print(f"💡 Decision: {decision.get('reason')}")

        # 3. Action
        execute_action(decision)

        # Track action history
        action_history.append(decision)

        # Wait for UI to update
        time.sleep(2)

if __name__ == "__main__":
    # Example Goal: "Open settings and turn on Wi-Fi"
    # Or your demo goal: "Find the 'Connect' button and tap it"
    GOAL = input("Enter your goal: ")
    run_agent(GOAL)