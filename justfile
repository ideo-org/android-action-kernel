set shell := ["sh", "-c"]
set windows-shell := ["powershell.exe", "-NoLogo", "-Command"]
#set allow-duplicate-recipe
#set positional-arguments
set dotenv-filename := ".env"
set export

import? "local.justfile"

RANDOM := env("RANDOM", "42")


setup:
  brew install android-platform-tools
  uv venv
  uv pip install -r requirements.txt
