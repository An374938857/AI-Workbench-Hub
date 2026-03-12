import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import embedding_governance


class DummyDB:
    def flush(self):
        return None


def test_update_embedding_config_creates_rebuild_task_even_when_model_unchanged(monkeypatch):
    created = []

    monkeypatch.setattr(embedding_governance, "_validate_embedding_model", lambda *args, **kwargs: None)
    monkeypatch.setattr(embedding_governance, "_set_config_int", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        embedding_governance,
        "get_embedding_config",
        lambda db: {
            "global_default_text_embedding_model_id": 101,
            "global_default_multimodal_embedding_model_id": None,
            "text_candidates": [],
            "multimodal_candidates": [],
        },
    )

    def fake_create_rebuild_task(db, embedding_type, target_model_id, trigger_user_id):
        created.append((embedding_type, target_model_id, trigger_user_id))
        return type("Task", (), {"id": len(created)})()

    monkeypatch.setattr(embedding_governance, "create_rebuild_task", fake_create_rebuild_task)

    payload = embedding_governance.update_embedding_config(
        db=DummyDB(),
        user_id=7,
        text_model_id=101,
        multimodal_model_id=None,
        rebuild_index=True,
    )

    assert created == [("TEXT", 101, 7)]
    assert payload["created_rebuild_tasks"] == [{"task_id": 1, "embedding_type": "TEXT"}]


def test_route_xlsx_assets_to_text():
    asset = SimpleNamespace(
        title="report.xlsx",
        file_ref="uploads/assets/report.xlsx",
        asset_type="FILE",
    )

    assert embedding_governance._route_asset(asset) == "TEXT"


def test_build_multimodal_input_for_image_asset(monkeypatch, tmp_path):
    image_path = tmp_path / "demo.png"
    image_path.write_bytes(b"fake-image-bytes")
    asset = SimpleNamespace(
        id=1,
        title="demo.png",
        file_ref="uploads/assets/demo.png",
        asset_type="FILE",
        scope_type="PROJECT",
        scope_id=1,
        node_code=None,
        snapshot_markdown="",
        content="",
    )
    monkeypatch.setattr(embedding_governance, "_asset_file_path", lambda _asset: image_path)

    prepared = embedding_governance._build_embedding_inputs(asset)

    assert prepared.route_type == "MULTIMODAL"
    assert prepared.multimodal_input["image"].startswith("data:image/png;base64,")
