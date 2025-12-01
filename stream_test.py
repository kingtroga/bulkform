import streamlit as st

# --- Basic Page Setup ---
st.set_page_config(
    page_title="Quick Streamlit App",
    page_icon="⚡",
    layout="centered"
)

# --- App Title ---
st.title("⚡ Quick Streamlit App")
st.write("This is a minimal Streamlit example — perfect for testing or demos!")

# --- Sidebar ---
st.sidebar.header("Settings")
name = st.sidebar.text_input("Enter your name:", "Tari")
show_confetti = st.sidebar.checkbox("Celebrate? 🎉", value=False)

# --- Main Content ---
st.subheader("Hello Section")
st.write(f"Hi **{name}**, welcome to your first Streamlit app!")

# --- Example Interaction ---
number = st.slider("Pick a number:", 1, 100, 25)
st.write(f"Your number squared is: **{number ** 2}**")

# --- Optional Celebration ---
if show_confetti:
    st.balloons()

# --- Footer ---
st.markdown("---")
st.caption("Built with ❤️ using [Streamlit](https://streamlit.io/)")
