import numpy as np
from PIL import Image, ImageDraw
import pytest
import background


def test_cutout_keeps_original_rgb_and_never_restores_transparent_pixels(tmp_path, monkeypatch):
    pixels = np.array([[[25, 80, 170, 255], [250, 240, 20, 0]],
                       [[50, 60, 70, 100], [10, 20, 30, 255]]], dtype=np.uint8)
    source, result = tmp_path / "source.png", tmp_path / "cutout.png"
    Image.fromarray(pixels).save(source)
    monkeypatch.setattr(background, "_predict_mask", lambda image: Image.fromarray(np.array([[128,255],[255,0]], dtype=np.uint8)))
    background.remove_background(source, result)
    actual = np.asarray(Image.open(result))
    np.testing.assert_array_equal(actual[:, :, :3], pixels[:, :, :3])
    np.testing.assert_array_equal(actual[:, :, 3], [[128,0],[100,0]])


def test_missing_model_has_actionable_error(tmp_path, monkeypatch):
    monkeypatch.setenv("STUDIO_MODEL_PATH", str(tmp_path / "missing.onnx"))
    monkeypatch.setattr(background, "_session", None)
    with pytest.raises(RuntimeError, match="Brak lokalnego modelu"):
        background._get_session()


def test_changed_model_is_not_loaded(tmp_path, monkeypatch):
    model = tmp_path / "changed.onnx"
    model.write_bytes(b"not the verified model")
    monkeypatch.setenv("STUDIO_MODEL_PATH", str(model))
    monkeypatch.setattr(background, "_session", None)
    with pytest.raises(RuntimeError, match="sumę kontrolną"):
        background._get_session()


def test_smart_cutout_recovers_a_thin_cable_missed_by_semantic_mask(tmp_path, monkeypatch):
    source, result = tmp_path / "source.png", tmp_path / "cutout.png"
    image = Image.new("RGB", (120, 100), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((30, 20, 75, 80), fill="#303030")
    draw.line((75, 65, 110, 65), fill="#303030", width=2)
    image.save(source)
    prediction = Image.new("L", image.size, 0)
    ImageDraw.Draw(prediction).rectangle((30, 20, 75, 80), fill=255)
    monkeypatch.setattr(background, "_predict_mask", lambda image: prediction)
    background.remove_background(source, result, method="smart")
    actual = np.asarray(Image.open(result))
    assert actual[65, 100, 3] == 255
    assert actual[0, 0, 3] == 0
    np.testing.assert_array_equal(actual[:, :, :3], np.asarray(image))


def test_smart_cutout_keeps_white_interior_and_clears_only_connected_background(tmp_path, monkeypatch):
    source, result = tmp_path / "source.png", tmp_path / "cutout.png"
    image = Image.new("RGB", (60, 60), "white")
    ImageDraw.Draw(image).rectangle((15, 15, 45, 45), outline="black", width=2)
    image.save(source)
    monkeypatch.setattr(background, "_predict_mask", lambda image: Image.new("L", image.size, 0))
    background.remove_background(source, result)
    alpha = np.asarray(Image.open(result))[:, :, 3]
    assert alpha[30, 30] == 255
    assert alpha[0, 30] == 0


@pytest.mark.parametrize("method", ["smart", "ai"])
def test_nonuniform_backdrop_preserves_semantic_prediction(tmp_path, monkeypatch, method):
    source, result = tmp_path / "source.png", tmp_path / "cutout.png"
    image = Image.new("RGB", (60, 60), "navy")
    ImageDraw.Draw(image).rectangle((30, 0, 59, 59), fill="orange")
    image.save(source)
    monkeypatch.setattr(background, "_predict_mask", lambda image: Image.new("L", image.size, 91))
    background.remove_background(source, result, method=method)
    assert np.all(np.asarray(Image.open(result))[:, :, 3] == 91)


def test_ai_method_retains_unmodified_model_mask(tmp_path, monkeypatch):
    source, result = tmp_path / "source.png", tmp_path / "cutout.png"
    image = Image.new("RGB", (60, 60), "white")
    ImageDraw.Draw(image).rectangle((15, 15, 45, 45), fill="black")
    image.save(source)
    monkeypatch.setattr(background, "_predict_mask", lambda image: Image.new("L", image.size, 91))
    background.remove_background(source, result, method="ai")
    assert np.all(np.asarray(Image.open(result))[:, :, 3] == 91)


def test_smart_cutout_does_not_invent_an_object_on_uniform_image(tmp_path, monkeypatch):
    source, result = tmp_path / "source.png", tmp_path / "cutout.png"
    Image.new("RGB", (60, 60), "white").save(source)
    monkeypatch.setattr(background, "_predict_mask", lambda image: Image.new("L", image.size, 127))
    with pytest.raises(ValueError, match="jednolite"):
        background.remove_background(source, result)
    assert not result.exists()


def test_cutout_rejects_unknown_method(tmp_path):
    with pytest.raises(ValueError, match="metoda"):
        background.remove_background(tmp_path / "missing.png", tmp_path / "out.png", method="unknown")


def test_connected_backdrop_stops_when_complexity_budget_is_exhausted():
    eligible = np.ones((20, 20), dtype=bool)
    assert background._connected_backdrop(eligible, max_spans=1) is None


def test_real_model_smart_mode_preserves_thin_dark_cable(tmp_path):
    source = tmp_path / "source.png"
    image = Image.new("RGB", (1400, 1000), "white")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((420, 270, 890, 780), radius=35, fill="#444444")
    draw.rectangle((455, 310, 855, 685), fill="#141414")
    draw.line([(890, 700), (1040, 700), (1070, 540), (1200, 540)], fill="#303030", width=4)
    image.save(source)
    result = tmp_path / "smart.png"
    background.remove_background(source, result, method="smart")
    actual = np.asarray(Image.open(result))
    assert np.median(actual[699:702, 920:1020, 3]) == 255
    assert actual[0, 0, 3] == 0
    np.testing.assert_array_equal(actual[:, :, :3], np.asarray(image))
