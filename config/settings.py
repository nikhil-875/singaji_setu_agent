import os
from dotenv import load_dotenv

# Load environment variables with error handling
try:
    load_dotenv(override=True)  # Add override=True to ensure variables are loaded
except Exception as e:
    print(f"Warning: Could not load .env file: {e}")
    print("Continuing with system environment variables...")

# Application settings
APP_TITLE = "Singaji Setu AGENT"
APP_ICON = "🌾"
APP_LAYOUT = "wide"

# Google Cloud settings
GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Google Cloud Storage settings
GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME")
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID")
GCP_LOCATION = os.getenv("GCP_LOCATION")


# Validate required environment variables
def validate_environment():
    """Validate that required environment variables are set."""
    missing_vars = []

    if not GOOGLE_APPLICATION_CREDENTIALS:
        missing_vars.append("GOOGLE_APPLICATION_CREDENTIALS")

    if not GEMINI_API_KEY:
        missing_vars.append("GEMINI_API_KEY")

    if missing_vars:
        print("⚠️  Missing required environment variables:")
        for var in missing_vars:
            print(f"   - {var}")
        print("\nPlease set these variables in your .env file or system environment.")
        print("See .env.example for reference.")

    return len(missing_vars) == 0


# Handle service account key for production (when it's Base64 encoded)
def get_service_account_credentials():
    """Resolve Google credentials from file path, raw JSON, or Base64 JSON."""
    value = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if not value:
        return None

    try:
        import os as _os
        import json as _json
        import base64 as _base64
        import tempfile as _tempfile

        value_str = value.strip()

        # 1) Treat as path if file exists
        if _os.path.exists(value_str):
            return value_str

        # 2) Treat as raw JSON string
        if value_str.startswith("{") and value_str.endswith("}"):
            try:
                _json.loads(value_str)
                tmp = _tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
                tmp.write(value_str)
                tmp.close()
                return tmp.name
            except Exception as json_error:
                print(f"Debug - Raw JSON credentials parse error: {json_error}")

        # 3) Treat as Base64/URL-safe Base64 encoded JSON
        cleaned = "".join(value_str.split())  # remove spaces and newlines
        # ensure base64 padding
        pad = len(cleaned) % 4
        if pad:
            cleaned += "=" * (4 - pad)

        for decoder in (_base64.b64decode, _base64.urlsafe_b64decode):
            try:
                decoded_bytes = decoder(cleaned)
                decoded_text = decoded_bytes.decode("utf-8")
                _json.loads(decoded_text)
                tmp = _tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
                tmp.write(decoded_text)
                tmp.close()
                return tmp.name
            except Exception:
                continue

        print("❌ GOOGLE_APPLICATION_CREDENTIALS is neither a file path, raw JSON, nor Base64-encoded JSON.")
        return None

    except Exception as e:
        print(f"❌ Error resolving GOOGLE_APPLICATION_CREDENTIALS: {e}")
        return None


def get_gcp_project_id():
    """Get GCP project ID from environment or service account credentials."""
    project_id = os.getenv("GCP_PROJECT_ID")
    if project_id:
        return project_id

    # Try to extract from service account credentials
    creds_path = get_service_account_credentials()
    if creds_path and os.path.exists(creds_path):
        try:
            import json

            with open(creds_path, "r") as f:
                creds_data = json.load(f)
                return creds_data.get("project_id")
        except Exception:
            pass

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
