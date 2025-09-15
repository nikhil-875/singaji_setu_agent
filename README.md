# 🌾 Singaji Setu AGENT

An intelligent agent to process farmer interview surveys from audio recordings using Google Cloud Speech-to-Text and Google Gemini AI.

## 🏗️ Project Structure

The application is now organized into a modular structure for better maintainability and code organization:

```
singaji_setu_agent/
├── main.py                          # Main application entry point
├── config/
│   ├── __init__.py
│   └── settings.py                  # Configuration and environment variables
├── services/
│   ├── __init__.py
│   ├── transcription_service.py     # Audio transcription service
│   └── gemini_service.py           # AI payload generation service
├── utils/
│   ├── __init__.py
│   ├── audio_processor.py          # Audio processing utilities
│   └── ui_components.py            # UI styling and components
├── ui/
│   └── __init__.py
├── requirements.txt                 # Python dependencies
├── pyproject.toml                  # Project configuration
└── README.md                       # This file
```

## 🚀 Features

- **Audio Transcription**: Convert audio files to text using Google Cloud Speech-to-Text
- **Smart Chunking**: Automatically split long audio files into manageable chunks
- **Live Dashboard**: Real-time transcription progress monitoring
- **Transcript Editing**: Review and edit transcripts before AI processing
- **AI-Powered Analysis**: Generate structured JSON payloads using Google Gemini
- **Extra Details Capture**: Automatically capture additional information not covered by the schema
- **Export Functionality**: Download transcripts and JSON payloads

## 📋 Prerequisites

1. **Python 3.8+**
2. **Google Cloud Account** with Speech-to-Text API enabled
3. **Google AI Studio API Key** for Gemini
4. **Service Account Key** for Google Cloud

## 🛠️ Installation

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd singaji_setu_agent
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   # or using uv (recommended)
   uv sync
   ```

3. **Set up environment variables:**
   Create a `.env` file in the root directory:
   ```env
   GOOGLE_APPLICATION_CREDENTIALS=path/to/your/service-account-key.json
   GOOGLE_API_KEY=your_gemini_api_key_here
   ```

4. **Place your service account key:**
   - Download your Google Cloud service account key
   - Place it in the project root as `service-account-key.json`
   - Or update the `.env` file with the correct path

## 🎯 Usage

1. **Run the application:**
   ```bash
   streamlit run main.py
   ```

2. **Choose Your Workflow:**
   - **Live Record Interview**: Record audio directly in your browser
   - **Import Audio File**: Upload existing audio files (WAV, MP3, M4A, FLAC)

3. **Process Audio:**
   - Record live audio or upload a file
   - Click "Start Transcription" to convert audio to text

4. **Review & Edit:**
   - Review the generated transcript
   - Edit if needed and save changes

5. **Generate Survey Data:**
   - Use AI to analyze the transcript
   - Generate structured JSON survey data

6. **Export Results:**
   - Download audio, transcript, and survey data
   - View summary of processed information

## 🔧 Configuration

### Audio Processing
- `MAX_SYNC_DURATION_SECONDS`: Maximum duration for each audio chunk (default: 59s)
- `SUPPORTED_AUDIO_FORMATS`: Supported audio file formats

### Speech Recognition
- `DEFAULT_LANGUAGE_CODE`: Default language for transcription (default: "hi-IN" for Hindi)
- `SPEECH_MODEL`: Speech recognition model (default: "telephony")

### AI Settings
- `GEMINI_MODEL`: Gemini model to use (default: "gemini-1.5-flash")
- `GEMINI_TEMPERATURE`: AI response creativity (default: 0.1)

## 📊 Schema Example

The default schema includes:
```json
{
  "farmer_name": "string",
  "village": "string",
  "contact_number": "string",
  "primary_crop": "string",
  "land_size_acres": "number",
  "soil_type": "string",
  "main_challenges": ["list of strings"],
  "interested_in_new_tech": "boolean",
  "extra_details": "object (key-value pairs of additional information)"
}
```

## 🔍 Extra Details

The AI automatically captures additional information found in transcripts that doesn't fit the defined schema. These are stored in the `extra_details` field as key-value pairs, such as:
- Weather conditions
- Family details
- Specific farming techniques
- Market information
- Any other relevant details

## 🏗️ Architecture

### Services Layer
- **TranscriptionService**: Handles audio transcription with chunking
- **GeminiService**: Manages AI-powered JSON payload generation

### Utilities Layer
- **Audio Processing**: Audio file chunking and format conversion
- **UI Components**: Styling, extra details display, and common UI functions

### UI Layer
- **Workflow Components**: Modular workflow rendering functions
- **Session Management**: Streamlit session state initialization

### Configuration Layer
- **Environment Variables**: Centralized configuration management
- **Constants**: Application-wide constants and settings

## 🚀 Benefits of Modular Structure

1. **Maintainability**: Easy to locate and modify specific functionality
2. **Reusability**: Services and utilities can be reused across different parts
3. **Testing**: Individual components can be tested in isolation
4. **Scalability**: Easy to add new features or modify existing ones
5. **Code Organization**: Clear separation of concerns
6. **Team Collaboration**: Multiple developers can work on different modules

## 🐛 Troubleshooting

### Common Issues

1. **Google Cloud Credentials Error:**
   - Ensure your service account key is properly placed
   - Check that the Speech-to-Text API is enabled

2. **Gemini API Error:**
   - Verify your Google AI Studio API key is correct
   - Check API quota and billing

3. **Audio Processing Error:**
   - Ensure the audio file is in a supported format
   - Check file size and duration

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## 📞 Support

For support and questions, please open an issue in the repository.
