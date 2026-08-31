from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_streamlit_app_starts_without_exceptions():
    app_path = Path(__file__).resolve().parents[1] / "app_v2.py"
    app = AppTest.from_file(app_path)
    app.run(timeout=30)
    assert not app.exception
    assert any("مجلس الذهب" in title.value for title in app.title)
