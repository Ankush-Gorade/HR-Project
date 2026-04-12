import streamlit as st
import os
import sys

# Get the absolute path of where the script is running
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# Try to import the pipeline
try:
    from pipeline.orchestrator import run_pipeline
    st.sidebar.success("✅ Pipeline modules loaded")
except ImportError as e:
    st.error(f"❌ Import Error: {e}")
    st.info("Check if 'langgraph' is installed and HR-Project folders are present.")

st.title("HR Multi-Agent Screener")

# ... (rest of your UI code)
