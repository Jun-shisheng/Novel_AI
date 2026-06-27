# Word AI Writing Assistant

Windows Word 2019 AI plugin using DeepSeek API for polish and auto-continue.

## Usage

```
Double-click start.bat → Switch to Word → Write
```

| Hotkey | Action |
|--------|--------|
| **Ctrl+E** | Polish/expand selected text |
| **Ctrl+Enter** | Start auto-continue / Stop |

## One-Time Setup

1. Install Python 3.11+ (from python.org)
2. Double-click `install.bat`, wait for completion
3. Right-click `start.bat` → Send to Desktop for quick access

## Config

API Key is pre-configured. To change it, edit `config/settings.json` after first run.

## Project Layout

```
G:\WordAI\
├── word_ai.py          # Main launcher (hotkeys + Word COM)
├── install.bat         # One-time setup
├── start.bat           # Daily launcher
├── backend/            # Python FastAPI server
├── config/             # Encrypted settings (G: drive)
└── .ai-writing/        # Summary database (G: drive)
```
