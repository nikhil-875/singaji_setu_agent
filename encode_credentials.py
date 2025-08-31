#!/usr/bin/env python3
"""
Helper script to encode service account JSON to Base64 format
for safer environment variable usage.
"""

import json
import base64
import os

def encode_json_to_base64():
    """Convert service-account-key.json to Base64 format."""
    
    json_file_path = "service-account-key.json"
    
    try:
        # Read the JSON file
        with open(json_file_path, 'r', encoding='utf-8') as file:
            json_content = file.read()
        
        # Parse to validate it's valid JSON
        json_data = json.loads(json_content)
        
        # Convert to compact string
        json_string = json.dumps(json_data, separators=(',', ':'))
        
        # Encode to Base64
        base64_encoded = base64.b64encode(json_string.encode('utf-8')).decode('utf-8')
        
        print("=" * 60)
        print("🔐 SERVICE ACCOUNT CREDENTIALS ENCODED TO BASE64")
        print("=" * 60)
        print()
        print("📋 For your .env file (local development):")
        print(f"GOOGLE_APPLICATION_CREDENTIALS={json_file_path}")
        print()
        print("📋 For production environment variables (Base64):")
        print(f"GOOGLE_APPLICATION_CREDENTIALS={base64_encoded}")
        print()
        print("📋 For Streamlit Cloud secrets:")
        print("GOOGLE_APPLICATION_CREDENTIALS = \"")
        print(base64_encoded)
        print("\"")
        print()
        print("=" * 60)
        print("✅ Base64 encoding completed successfully!")
        print("=" * 60)
        
        return base64_encoded
        
    except FileNotFoundError:
        print(f"❌ Error: {json_file_path} not found!")
        print("Make sure the file exists in the current directory.")
        return None
    except json.JSONDecodeError as e:
        print(f"❌ Error: Invalid JSON in {json_file_path}: {e}")
        return None
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return None

def create_env_examples():
    """Create example environment files."""
    
    base64_encoded = encode_json_to_base64()
    if not base64_encoded:
        return
    
    # Create .env.example
    env_example_content = f"""# Copy this file to .env and fill in your actual values
# NEVER commit .env file to Git!

# Google Cloud credentials
# For local development: path to your service account key file
GOOGLE_APPLICATION_CREDENTIALS=service-account-key.json

# For production: Base64 encoded JSON content
# GOOGLE_APPLICATION_CREDENTIALS={base64_encoded}

# Google Gemini API key
GOOGLE_API_KEY=your_gemini_api_key_here
"""
    
    try:
        with open('.env.example', 'w', encoding='utf-8') as f:
            f.write(env_example_content)
        print("✅ Created .env.example file")
    except Exception as e:
        print(f"❌ Could not create .env.example: {e}")

if __name__ == "__main__":
    print("🚀 Encoding service account credentials to Base64...")
    encode_json_to_base64()
    print()
    create_env_examples()
