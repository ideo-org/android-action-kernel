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

# Bedrock client (lazy loaded)
bedrock_client = None

def get_bedrock_client():
    """Initialize Bedrock client if needed."""
    global bedrock_client
    if bedrock_client is None:
        import boto3
        # Uses default AWS credential chain:
        # 1. Environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
        # 2. ~/.aws/credentials file (from 'aws configure')
        # 3. IAM role (if running on AWS)
        bedrock_client = boto3.client(
            service_name="bedrock-runtime",
            region_name=os.environ.get("AWS_REGION", "us-east-1")
        )
    return bedrock_client

# --- CONFIGURATION ---
ADB_PATH = "adb"  # Ensure adb is in your PATH
SCREEN_DUMP_PATH = "/sdcard/window_dump.xml"
LOCAL_DUMP_PATH = "window_dump.xml"

# LLM Provider: "groq", "openai", or "bedrock"
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "groq")
client = None  # OpenAI client (not used for Bedrock)

if LLM_PROVIDER == "groq":
    MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
    client = OpenAI(
        api_key=os.environ.get("GROQ_API_KEY"),
        base_url="https://api.groq.com/openai/v1"
    )
elif LLM_PROVIDER == "bedrock":
    MODEL = os.environ.get("BEDROCK_MODEL", "anthropic.claude-3-sonnet-20240229-v1:0")
else:
    MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o")
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
        
    elif act_type == "enter":
        print("⏎ Pressing Enter")
        run_adb_command(["shell", "input", "keyevent", "66"])  # KEYCODE_ENTER

    elif act_type == "swipe":
        direction = action.get("direction", "up")
        # Screen center coordinates (adjust based on device)
        cx, cy = 540, 1200
        if direction == "up":
            print("👆 Swiping Up")
            run_adb_command(["shell", "input", "swipe", str(cx), "1500", str(cx), "500", "300"])
        elif direction == "down":
            print("👇 Swiping Down")
            run_adb_command(["shell", "input", "swipe", str(cx), "500", str(cx), "1500", "300"])
        elif direction == "left":
            print("👈 Swiping Left")
            run_adb_command(["shell", "input", "swipe", "800", str(cy), "200", str(cy), "300"])
        elif direction == "right":
            print("👉 Swiping Right")
            run_adb_command(["shell", "input", "swipe", "200", str(cy), "800", str(cy), "300"])

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
    - {"action": "enter", "reason": "Press Enter to submit/search"}
    - {"action": "swipe", "direction": "up/down/left/right", "reason": "Why you are swiping"}
    - {"action": "home", "reason": "Go to home screen"}
    - {"action": "back", "reason": "Go back"}
    - {"action": "wait", "reason": "Wait for loading"}
    - {"action": "done", "reason": "Task complete"}

    IMPORTANT RULES:
    - If an element has "editable": true or "action": "type", use the "type" action to enter text.
    - After tapping on a text field, your NEXT action should be "type" to enter text.
    - After typing a URL or search query, use "enter" to submit it.
    - Do NOT type the same text again if you already typed it in a previous step. Check PREVIOUS_ACTIONS.
    - Do NOT tap the same element repeatedly. If you already tapped it, try a different action.
    - If the screen shows your typed text, do NOT type again - use "enter" or tap a search result.
    - If you need to find an app that's not on the home screen, swipe UP to open the app drawer.
    - Use swipe to scroll through lists, pages, or to open the app drawer.

    Example - Tapping a button:
    {"action": "tap", "coordinates": [540, 1200], "reason": "Clicking the 'Connect' button"}

    Example - Typing in a search box:
    {"action": "type", "text": "White House", "reason": "Entering search query"}

    Example - After typing a URL:
    {"action": "enter", "reason": "Submitting the URL to navigate"}

    Example - Opening app drawer to find an app:
    {"action": "swipe", "direction": "up", "reason": "Opening app drawer to find Maps"}
    """

    # Format action history with details
    history_str = ""
    if action_history:
        history_lines = []
        for i, a in enumerate(action_history):
            action_type = a['action']
            reason = a.get('reason', 'N/A')
            if action_type == 'type':
                history_lines.append(f"Step {i+1}: typed \"{a.get('text', '')}\" - {reason}")
            elif action_type == 'tap':
                history_lines.append(f"Step {i+1}: tapped {a.get('coordinates', [])} - {reason}")
            else:
                history_lines.append(f"Step {i+1}: {action_type} - {reason}")
        history_str = "\n\nPREVIOUS_ACTIONS:\n" + "\n".join(history_lines)

    user_content = f"GOAL: {goal}\n\nSCREEN_CONTEXT:\n{screen_context}{history_str}"

    if LLM_PROVIDER == "bedrock":
        # Use AWS Bedrock API
        bedrock = get_bedrock_client()

        # Prepare request based on model type
        if "anthropic" in MODEL:
            # Anthropic Claude format
            request_body = json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 1024,
                "system": system_prompt,
                "messages": [
                    {"role": "user", "content": user_content + "\n\nRespond with ONLY a valid JSON object."}
                ]
            })
        elif "meta" in MODEL or "llama" in MODEL.lower():
            # Meta Llama 3.x format (newer models use different format)
            request_body = json.dumps({
                "prompt": f"<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n\n{system_prompt}<|eot_id|><|start_header_id|>user<|end_header_id|>\n\n{user_content}\n\nRespond with ONLY a valid JSON object, no other text.<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n\n",
                "max_gen_len": 512,
                "temperature": 0.1
            })
        else:
            # Amazon Titan or other models
            request_body = json.dumps({
                "inputText": f"{system_prompt}\n\n{user_content}\n\nRespond with ONLY a valid JSON object.",
                "textGenerationConfig": {
                    "maxTokenCount": 512,
                    "temperature": 0.1
                }
            })

        response = bedrock.invoke_model(
            modelId=MODEL,
            body=request_body,
            contentType="application/json",
            accept="application/json"
        )

        response_body = json.loads(response["body"].read())

        # Extract text based on model type
        if "anthropic" in MODEL:
            result_text = response_body["content"][0]["text"]
        elif "meta" in MODEL or "llama" in MODEL.lower():
            result_text = response_body.get("generation", "")
        else:
            result_text = response_body["results"][0]["outputText"]

        # Try to extract JSON from response (model may include extra text)
        try:
            return json.loads(result_text)
        except json.JSONDecodeError:
            # Try to find JSON object in the response
            import re
            json_match = re.search(r'\{[^{}]*\}', result_text)
            if json_match:
                return json.loads(json_match.group())
            else:
                print(f"⚠️ Could not parse LLM response: {result_text[:200]}")
                return {"action": "wait", "reason": "Failed to parse response, waiting"}
    else:
        # Use OpenAI-compatible API (OpenAI, Groq)
        response = client.chat.completions.create(
            model=MODEL,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
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