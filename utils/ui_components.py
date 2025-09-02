import streamlit as st
from typing import Dict, Any


def apply_custom_styling():
    """Apply custom CSS styling for the application."""
    theme_base = st.get_option("theme.base")
    primary_color = "#2E7D32"  # A nice green for the farmer theme
    hover_color = "#A5D6A7" if theme_base == "light" else "#4CAF50"
    secondary_bg_color = "#FFFFFF" if theme_base == "light" else "#1E1E1E"

    st.markdown(
        f"""
    <style>
    .stApp {{ background-color: {"#f0f2f6" if theme_base == "light" else "#0F0F0F"}; }}
    .stTabs [data-baseweb="tab-list"] {{ gap: 24px; }}
    .stTabs [data-baseweb="tab"] {{
        background-color: {secondary_bg_color}; border-radius: 4px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1); padding: 10px 20px;
    }}
    .stTabs [data-baseweb="tab"]:hover {{
        background-color: {hover_color};
        color: {"#000000" if theme_base == "light" else "#FFFFFF"};
    }}
    .stTabs [aria-selected="true"] {{ background-color: {primary_color}; color: white; }}
    .stButton>button {{
        background-color: {primary_color}; color: white; border-radius: 20px;
        padding: 10px 20px; border: none; box-shadow: 0 2px 4px rgba(0,0,0,0.2);
    }}
    /* Target focused text area to remove red border */
    textarea:focus {{
        border-color: {primary_color} !important;
        box-shadow: 0 0 0 1px {primary_color} !important;
    }}
    </style>
    """,
        unsafe_allow_html=True,
    )


def display_extra_details(gemini_result: Dict[str, Any]):
    """Display extra details found in the Gemini result in an organized way."""
    if "extra_details" in gemini_result and gemini_result["extra_details"]:
        st.subheader("🔍 Extra Details Found:")
        extra_details = gemini_result["extra_details"]

        if isinstance(extra_details, dict):
            for key, value in extra_details.items():
                if value is not None and value != "":
                    st.markdown(f"**{key}:** {value}")
        elif isinstance(extra_details, list):
            for item in extra_details:
                if item:
                    st.markdown(f"• {item}")
        else:
            st.markdown(f"**Additional Information:** {extra_details}")


def get_default_schema() -> Dict[str, Any]:
    """
    Provides a default nested JSON schema for extracting details
    from a farmer's interview.
    """
    return {
        "farmerDetails": {
            "farmerName": "string (Full name of the farmer)",
            "village": "string (Village, Tehsil, and District if available)",
            "contactNumber": "string (10-digit mobile number, if provided)",
            "farmingExperienceYears": "number (Number of years in farming)",
            "householdSize": "number (Total number of family members)",
        },
        "farmDetails": {
            "totalLandSizeAcres": "number (Total acres of land owned or farmed)",
            "soilType": "string (e.g., 'Black', 'Red', 'Alluvial', 'Loam')",
            "primaryCrops": [
                "list of strings (Main crops grown, e.g., 'Wheat', 'Cotton')"
            ],
            "irrigationSource": "string (e.g., 'Canal', 'Well', 'Borewell', 'Rain-fed')",
        },
        "livestockDetails": {
            "hasLivestock": "boolean (Does the farmer own any farm animals?)",
            "animals": [
                {
                    "type": "string (e.g., 'Cow', 'Buffalo', 'Goat', 'Chicken')",
                    "count": "number (The number of animals of this type)",
                }
            ],
        },
        "challengesAndNeeds": {
            "mainChallenges": [
                "list of strings (Primary difficulties faced, e.g., 'Pest attacks', 'Low water', 'Market price')"
            ],
            "interestedInNewTech": "boolean (Is the farmer open to trying new technology or methods?)",
            "specificNeeds": [
                "list of strings (Specific help they are looking for, e.g., 'Loan information', 'Better seeds')"
            ],
        },
        "interviewMetadata": {
            "interviewerName": "string (Name of the person conducting the interview)",
            "interviewDate": "string (Date of the interview in YYYY-MM-DD format)",
            "summary": "string (A brief, 2-3 sentence summary of the entire conversation)",
        },
    }
