# Hugging Face Spaces entrypoint.
#
# When this directory is uploaded as a Gradio Space, HF runs app.py and
# installs requirements.txt. See DEPLOY.md for the full setup.

from lgmt.webapp import build_app

if __name__ == "__main__":
    build_app().launch()
