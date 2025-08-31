import streamlit as st
import os
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional

# Constants
GEMINI_MODEL = "gemini-1.5-flash"

class GeminiService:
    """Handles intelligent JSON payload generation for farmer surveys."""

    def __init__(self):
        self.llm = self._initialize_llm()

    def _initialize_llm(self) -> Optional[ChatGoogleGenerativeAI]:
        if not os.getenv("GOOGLE_API_KEY"):
            st.error("❌ Google API key not found. Please set it in your .env file.")
            return None
        try:
            return ChatGoogleGenerativeAI(model=GEMINI_MODEL, temperature=0.1)
        except Exception as e:
            st.error(f"Failed to initialize Gemini model: {e}")
            return None

    def generate_json_payload(
        self, schema: str, transcript: str
    ) -> Optional[Dict[str, Any]]:
        """Generates a structured JSON payload from a transcript based on a provided schema."""
        if not self.llm:
            return None
        try:
            with st.spinner(
                "🧠 Gemini is analyzing the interview to generate the JSON payload..."
            ):
                # Define a dynamic Pydantic model for the parser
                class DynamicSchema(BaseModel):
                    payload: Dict[str, Any] = Field(
                        description="The final JSON payload based on the user's schema"
                    )

                parser = JsonOutputParser(pydantic_object=DynamicSchema)

                prompt_template = """
                You are an expert data entry agent specializing in agricultural surveys in India.
                Your task is to analyze the following interview transcript and populate a JSON object based on the provided schema.

                **Instructions:**
                1.  Read the entire transcript carefully to understand the context of the farmer's interview.
                2.  Fill in the JSON fields based **only** on the information present in the transcript.
                3.  If a field from the schema is **not mentioned** in the transcript, you MUST use a `null` value for that field. Do not make up information.
                4.  If the transcript contains important details that **do not fit** into any of the schema fields, add them to a separate key called `extra_details` as key-value pairs.
                5.  The `extra_details` should contain all additional information found in the transcript that wasn't covered by the schema.
                6.  Ensure the final output is a single, valid JSON object.

                **JSON Schema to follow:**
                ```json
                {schema}
                ```

                **Interview Transcript:**
                ```text
                {transcript}
                ```

                **Your JSON Output:**
                {format_instructions}
                """
                prompt = ChatPromptTemplate.from_template(
                    template=prompt_template,
                    partial_variables={
                        "format_instructions": parser.get_format_instructions()
                    },
                )

                chain = prompt | self.llm | parser
                response = chain.invoke({"schema": schema, "transcript": transcript})

            st.success("✅ Gemini has successfully generated the JSON payload!")
            # The parser wraps the result in a 'payload' key, so we extract it.
            return response.get("payload", {})
        except Exception as e:
            st.error(f"Failed to generate JSON payload with Gemini: {e}")
            return None
