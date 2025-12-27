import streamlit as st
import sqlite3
import datetime
from google import genai
import pandas as pd

# --- CONFIGURATION ---
DB_FILE = "daily_aar.db"

# Try to get the key from Streamlit Secrets (Cloud), otherwise use local fallback
try:
    MY_API_KEY = st.secrets["GOOGLE_API_KEY"]
except:
    # If running locally on your machine, paste your key here for testing
    MY_API_KEY = "PASTE_YOUR_GOOGLE_API_KEY_HERE"

# --- SETUP & STYLING ---
st.set_page_config(page_title="Daily AAR", page_icon="🚀", layout="centered")

# --- INITIALIZE DATABASE (MOVED TO TOP) ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS aars (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            date_logged TEXT,
            time_logged TEXT,
            went_right TEXT,
            went_wrong TEXT,
            next_steps TEXT
        )
    ''')
    conn.commit()
    conn.close()

# Run this immediately so the table exists before we try to read it
init_db()

# --- AI CLIENT ---
@st.cache_resource
def get_ai_client():
    try:
        return genai.Client(api_key=MY_API_KEY)
    except:
        return None

client = get_ai_client()

# --- DATABASE FUNCTIONS ---
def save_to_db(user, right, wrong, next_time):
    now = datetime.datetime.now()
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''
            INSERT INTO aars (username, date_logged, time_logged, went_right, went_wrong, next_steps)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user, now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"), right, wrong, next_time))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"Database Error: {e}")
        return False

def load_history(user=None):
    conn = sqlite3.connect(DB_FILE)
    # We use a try/except block here just in case pandas has trouble reading an empty DB
    try:
        query = "SELECT * FROM aars ORDER BY id DESC"
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        if user:
            df = df[df['username'] == user]
        return df
    except Exception as e:
        conn.close()
        return pd.DataFrame() # Return empty table if it fails

def generate_ai_tip(user):
    if not client:
        return "AI Error: Client not connected."
    
    df = load_history(user).head(5)
    
    if df.empty:
        return "Log more entries to get AI coaching!"

    history_text = ""
    for index, row in df.iterrows():
        history_text += f"- Date: {row['date_logged']}\n  Went Wrong: {row['went_wrong']}\n  Went Right: {row['went_right']}\n\n"

    prompt = f"""
    You are an expert Agile Team Coach.
    Analyze these recent AARs for user {user}:
    
    {history_text}
    
    TASK:
    Identify the underlying pattern of what is going wrong.
    Provide ONE specific, actionable, and short tip (under 50 words) to help them improve tomorrow.
    """
    
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash", 
            contents=prompt
        )
        return response.text
    except Exception as e:
        return f"AI Connection Error: {e}"

# --- THE WEBSITE LAYOUT ---

st.sidebar.header("User Settings")
team_members = ["Select Name...", "Kyle", "Sarah", "Mike", "Admin"]
current_user = st.sidebar.selectbox("Who are you?", team_members)

st.title("🚀 Team Daily AAR")
st.markdown(f"**Date:** {datetime.datetime.now().strftime('%A, %B %d, %Y')}")

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
                    success = save_to_db(current_user, right, wrong, next_time)
                    if success:
                        st.success("Entry Saved!")
                        with st.spinner("Analyzing your patterns..."):
                            tip = generate_ai_tip(current_user)
                            st.info(f"💡 **AI Coach:** {tip}")

# --- TAB 2: VIEW HISTORY ---
with tab2:
    st.header("Team History")
    filter_user = st.selectbox("Filter by User:", ["All Users"] + team_members[1:])
    
    if filter_user == "All Users":
        df = load_history()
    else:
        df = load_history(filter_user)

    if df.empty:
        st.write("No records found.")
    else:
        st.dataframe(
            df[['date_logged', 'username', 'went_right', 'went_wrong', 'next_steps']],
            use_container_width=True,
            hide_index=True
        )