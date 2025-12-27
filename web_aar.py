import streamlit as st
import datetime
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from google import genai

# --- CONFIGURATION ---
SHEET_NAME = "Daily_AAR_DB"  # The exact name of your Google Sheet

# --- SETUP & STYLING ---
st.set_page_config(page_title="Team AAR", page_icon="🚀", layout="centered")

# --- AUTHENTICATION & CONNECTIONS ---

# 1. Google Sheets Connection (Cached to avoid reconnecting every time)
@st.cache_resource
def get_gspread_client():
    # Load credentials from Streamlit Secrets
    try:
        # We access the 'gcp_service_account' section from secrets.toml
        secrets_dict = st.secrets["gcp_service_account"]
        
        # Define the scope (what we are allowed to do)
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        
        # Create credentials object
        creds = Credentials.from_service_account_info(secrets_dict, scopes=scopes)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"❌ Could not connect to Google Sheets: {e}")
        return None

# 2. AI Connection
@st.cache_resource
def get_ai_client():
    try:
        return genai.Client(api_key=st.secrets["GOOGLE_API_KEY"])
    except:
        return None

# --- DATABASE FUNCTIONS (Replaced SQLite with GSpread) ---

def init_sheet_headers(client):
    """Checks if the sheet is empty and adds headers if needed."""
    try:
        sheet = client.open(SHEET_NAME).sheet1
        # If cell A1 is empty, we assume it's a new sheet
        if not sheet.acell('A1').value:
            sheet.append_row([
                "Date", "Time", "User", "Went Right", "Went Wrong", "Next Steps"
            ])
    except Exception as e:
        st.warning(f"Could not initialize sheet headers: {e}")

def save_to_sheet(client, user, right, wrong, next_time):
    now = datetime.datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")
    
    try:
        sheet = client.open(SHEET_NAME).sheet1
        # Atomic append - safe for multiple users
        sheet.append_row([
            date_str, time_str, user, right, wrong, next_time
        ])
        return True
    except Exception as e:
        st.error(f"Failed to save to Google Sheet: {e}")
        return False

def load_history_from_sheet(client, user_filter=None):
    try:
        sheet = client.open(SHEET_NAME).sheet1
        # Get all records as a list of dictionaries
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        
        if df.empty:
            return df
            
        # Filter by user if requested
        if user_filter and user_filter != "All Users":
            df = df[df['User'] == user_filter]
            
        # Sort by Date descending (since sheet append adds to bottom, we flip it)
        # Note: In a real app, you might want a proper ID column, but this works
        return df.iloc[::-1] 
        
    except Exception as e:
        st.error(f"Could not load history: {e}")
        return pd.DataFrame()

def generate_ai_tip(ai_client, history_df, user):
    if not ai_client:
        return "AI Error: Client not connected."
    
    if history_df.empty:
        return "Log more entries to get AI coaching!"

    # Take the last 5 entries (from the top of our reversed dataframe)
    recent_history = history_df.head(5)
    
    history_text = ""
    for index, row in recent_history.iterrows():
        # Handle cases where column names might vary slightly
        w_wrong = row.get('Went Wrong', '')
        w_right = row.get('Went Right', '')
        date_val = row.get('Date', '')
        history_text += f"- Date: {date_val}\n  Went Wrong: {w_wrong}\n  Went Right: {w_right}\n\n"

    prompt = f"""
    You are an expert Agile Team Coach.
    Analyze these recent AARs for user {user}:
    
    {history_text}
    
    TASK:
    Identify the underlying pattern of what is going wrong.
    Provide ONE specific, actionable, and short tip (under 50 words) to help them improve tomorrow.
    """
    
    try:
        # Use stable model
        response = ai_client.models.generate_content(
            model="gemini-1.5-flash", 
            contents=prompt
        )
        return response.text
    except Exception as e:
        return f"AI Connection Error: {e}"

# --- MAIN APP LOGIC ---

# Initialize Clients
gs_client = get_gspread_client()
ai_client = get_ai_client()

if gs_client:
    init_sheet_headers(gs_client)

st.sidebar.header("User Settings")
team_members = ["Select Name...", "Kyle", "Sarah", "Mike", "Admin"]
current_user = st.sidebar.selectbox("Who are you?", team_members)

st.title("🚀 Team Daily AAR (Cloud DB)")
st.caption(f"Connected to: {SHEET_NAME}")

tab1, tab2 = st.tabs(["📝 Log Entry", "📜 View History"])

# --- TAB 1: LOG ENTRY ---
with tab1:
    if current_user == "Select Name...":
        st.warning("Please select your name in the sidebar to start.")
    else:
        with st.form("aar_form"):
            st.write(f"Logging as: **{current_user}**")
            right = st.text_area("1. What went right?", height=100)
            wrong = st.text_area("2. What went wrong?", height=100)
            next_time = st.text_area("3. What should we do differently?", height=100)
            
            submitted = st.form_submit_button("Save & Analyze", type="primary")
            
            if submitted:
                if not right and not wrong:
                    st.error("Please fill out at least one field.")
                else:
                    if gs_client:
                        with st.spinner("Saving to Google Sheets..."):
                            success = save_to_sheet(gs_client, current_user, right, wrong, next_time)
                            
                        if success:
                            st.success("Entry Saved to Cloud!")
                            
                            # AI Analysis
                            with st.spinner("Analyzing your patterns..."):
                                # Reload history to include the new entry for the AI
                                history_df = load_history_from_sheet(gs_client, current_user)
                                tip = generate_ai_tip(ai_client, history_df, current_user)
                                st.info(f"💡 **AI Coach:** {tip}")

# --- TAB 2: VIEW HISTORY ---
with tab2:
    if gs_client:
        filter_user = st.selectbox("Filter by User:", ["All Users"] + team_members[1:])
        
        df = load_history_from_sheet(gs_client, filter_user)

        if df.empty:
            st.info("No records found in the Google Sheet yet.")
        else:
            st.dataframe(
                df,
                use_container_width=True,
                hide_index=True
            )
