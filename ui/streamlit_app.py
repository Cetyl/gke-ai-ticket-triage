import os

import requests
import streamlit as st

# Point this at the API Gateway. With port-forward it is localhost:8000.
API_URL = os.getenv("API_URL", "http://localhost:8000")

st.set_page_config(page_title="AI Ticket Triage", page_icon="🎫")
st.title("AI Ticket Triage")
st.caption("Submit a support ticket. It is classified by your local Ollama model, "
           "stored, and routed by priority. Watch it light up in Grafana.")

with st.form("ticket"):
    subject = st.text_input("Subject", "Cannot log in to my account")
    body = st.text_area("Body", "I keep getting an error when I enter my password. "
                                "This is blocking my whole team.")
    submitted = st.form_submit_button("Submit ticket")

if submitted:
    with st.spinner("Classifying on your local model..."):
        try:
            resp = requests.post(f"{API_URL}/tickets",
                                 json={"subject": subject, "body": body}, timeout=140)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            st.error(f"Request failed: {exc}")
            st.stop()

    c = data["classification"]
    r = data["routing"]

    col1, col2, col3 = st.columns(3)
    col1.metric("Category", c.get("category", "?"))
    col2.metric("Urgency", c.get("urgency", "?"))
    col3.metric("Priority", r.get("priority", "?"))

    if not c.get("ai_ok", True):
        st.warning("Local model did not respond. Check the tunnel and that Ollama is running. "
                   "A safe fallback classification was used.")
    else:
        st.success(f"Classified by {c.get('model')} and stored "
                   f"({r.get('storage', {}).get('backend')}).")

    with st.expander("Raw response"):
        st.json(data)
