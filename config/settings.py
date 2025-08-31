import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Application settings
APP_TITLE = "Singaji Setu AGENT"
APP_ICON = "🌾"
APP_LAYOUT = "wide"

# Google Cloud settings
GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# Handle service account key for production (when it's Base64 encoded)
def get_service_account_credentials():
    """Get service account credentials for Google Cloud."""
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if not creds_path:
        return None
    
    # If it's a file path (local development)
    if os.path.exists(creds_path):
        return creds_path
    
    # If it's Base64 encoded (production)
    try:
        import base64
        import json
        import tempfile
        
        # Try to decode from Base64
        decoded_json = base64.b64decode(creds_path).decode('utf-8')
        
        # Validate it's valid JSON
        json.loads(decoded_json)
        
        # Create temporary file with the decoded JSON content
        temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
        temp_file.write(decoded_json)
        temp_file.close()
        return temp_file.name
        
    except (base64.binascii.Error, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        # If Base64 decoding fails, try as regular JSON string (fallback)
        try:
            import json
            import tempfile
            
            # Try to parse as JSON string
            json.loads(creds_path)
            
            # Create temporary file with the JSON content
            temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
            temp_file.write(creds_path)
            temp_file.close()
            return temp_file.name
            
        except (json.JSONDecodeError, ValueError):
            return None

# Gemini settings
GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_TEMPERATURE = 0.1

# Audio processing settings
MAX_SYNC_DURATION_SECONDS = 59
SUPPORTED_AUDIO_FORMATS = ["wav", "mp3", "m4a", "flac"]

# Speech recognition settings
DEFAULT_LANGUAGE_CODE = "hi-IN"
SPEECH_MODEL = "telephony"

# UI settings
PRIMARY_COLOR = "#2E7D32"  # Green for farmer theme
