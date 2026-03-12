from pathlib import Path


def test_files_router_exposes_icon_endpoint():
    router_file = Path(__file__).resolve().parents[1] / "app" / "routers" / "files.py"
    content = router_file.read_text(encoding="utf-8")

    assert '@router.get("/icons/{filename}")' in content
