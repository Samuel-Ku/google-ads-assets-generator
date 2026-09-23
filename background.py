"""Local U²-NetP inference. No network access during requests; original RGB is retained."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import threading
from collections import deque

import numpy as np
from PIL import Image, ImageOps

MODEL_SHA256 = "309c8469258dda742793dce0ebea8e6dd393174f89934733ecc8b14c76f4ddd8"
_session = None
_session_lock = threading.Lock()


def model_path() -> Path:
    return Path(os.environ.get("STUDIO_MODEL_PATH", Path(__file__).parent / "models/u2netp.onnx"))


def _get_session():
    global _session
    with _session_lock:
        if _session is None:
            path = model_path()
            if not path.is_file():
                raise RuntimeError("Brak lokalnego modelu usuwania tła. Skontaktuj się z administratorem.")
            if hashlib.sha256(path.read_bytes()).hexdigest() != MODEL_SHA256:
                raise RuntimeError("Model usuwania tła ma nieprawidłową sumę kontrolną.")
            import onnxruntime as ort
            ort.disable_telemetry_events()
            options = ort.SessionOptions()
            options.intra_op_num_threads = 2
            options.inter_op_num_threads = 1
            options.log_severity_level = 3
            _session = ort.InferenceSession(str(path), sess_options=options, providers=["CPUExecutionProvider"])
        return _session


def _predict_mask(image: Image.Image) -> Image.Image:
    # Composite existing transparency against white only for inference, not output.
    rgb = Image.new("RGBA", image.size, "white")
    rgb.alpha_composite(image)
    resized = rgb.convert("RGB").resize((320, 320), Image.Resampling.LANCZOS)
    values = np.asarray(resized, dtype=np.float32)
    values /= max(float(values.max()), 1.0)
    values = (values - np.array([.485, .456, .406], dtype=np.float32)) / np.array([.229, .224, .225], dtype=np.float32)
    tensor = np.ascontiguousarray(values.transpose(2, 0, 1)[None], dtype=np.float32)
    session = _get_session()
    prediction = np.asarray(session.run(None, {session.get_inputs()[0].name: tensor})[0][0, 0], dtype=np.float32)
    low, high = float(prediction.min()), float(prediction.max())
    if not np.isfinite(prediction).all() or high - low < 1e-6:
        raise RuntimeError("Nie udało się rozpoznać obiektu. Spróbuj innego zdjęcia z wyraźnym tłem.")
    alpha = np.clip((prediction - low) / (high - low) * 255, 0, 255).astype(np.uint8)
    return Image.fromarray(alpha).resize(image.size, Image.Resampling.LANCZOS)


def _connected_backdrop(eligible: np.ndarray, *, max_spans: int = 60_000):
    """Flood from the edges using native-resolution row spans, with a work budget.

    Unlike a global color key, this leaves a white product interior alone. A
    fragmented/noisy photograph may exceed the budget; callers then use the
    semantic mask without trying a slower or less reliable fallback.
    """
    height, width = eligible.shape
    reached = np.zeros_like(eligible)
    pending = deque()
    for x in np.flatnonzero(eligible[0]):
        pending.append((0, int(x)))
    for x in np.flatnonzero(eligible[-1]):
        pending.append((height - 1, int(x)))
    for y in np.flatnonzero(eligible[:, 0]):
        pending.append((int(y), 0))
    for y in np.flatnonzero(eligible[:, -1]):
        pending.append((int(y), width - 1))
    spans = 0
    while pending:
        y, x = pending.pop()
        if reached[y, x] or not eligible[y, x]:
            continue
        spans += 1
        if spans > max_spans or len(pending) > max_spans:
            return None
        barriers = np.flatnonzero(~eligible[y, :x])
        left = int(barriers[-1]) + 1 if barriers.size else 0
        barriers = np.flatnonzero(~eligible[y, x + 1:])
        right = x + 1 + int(barriers[0]) if barriers.size else width
        reached[y, left:right] = True
        for next_y in (y - 1, y + 1):
            if next_y < 0 or next_y >= height:
                continue
            candidates = eligible[next_y, left:right] & ~reached[next_y, left:right]
            starts = np.flatnonzero(candidates & ~np.r_[False, candidates[:-1]])
            pending.extend((next_y, left + int(offset)) for offset in starts)
    return reached


def _protected_details(image: Image.Image):
    """Find details a 320 px semantic model may miss on a uniform backdrop.

    This is deliberately conservative: it can retain a shadow, which the user
    can erase or avoid with AI-only mode, rather than erase a thin cable. No
    recovery is attempted on transparent images or inconsistent edge colors.
    """
    width, height = image.size
    if min(width, height) < 3 or max(width, height) > 20_000:
        return None
    extrema = image.getextrema()
    if extrema[3] != (255, 255):
        return None
    if all(high - low <= 2 for low, high in extrema[:3]):
        raise ValueError("Zdjęcie jest jednolite. Wybierz zdjęcie z widocznym produktem albo popraw maskę ręcznie.")
    pixels = np.asarray(image)
    border = np.concatenate((pixels[0, :, :3], pixels[-1, :, :3], pixels[:, 0, :3], pixels[:, -1, :3]))
    backdrop = np.median(border, axis=0).astype(np.int16)
    differences = np.max(np.abs(border.astype(np.int16) - backdrop), axis=1)
    if np.mean(differences <= 12) < .95:
        return None
    eligible = np.ones((height, width), dtype=bool)
    # Compare one channel at a time to avoid a full-resolution float/RGB tensor.
    for channel in range(3):
        eligible &= np.abs(pixels[:, :, channel].astype(np.int16) - backdrop[channel]) <= 18
    exterior = _connected_backdrop(eligible)
    if exterior is None:
        return None
    return ~exterior


def remove_background(input_path: Path, output_path: Path, *, method: str = "smart") -> None:
    """Write RGBA PNG; smart mode protects details on uniform backgrounds.

    ``ai`` retains the original semantic-only behavior. Both modes preserve RGB
    exactly and multiply their mask by the source alpha, never expanding it.
    """
    if method not in ("smart", "ai"):
        raise ValueError("Nieznana metoda usuwania tła.")
    with Image.open(input_path) as source:
        if source.width * source.height > 20_000_000:
            raise ValueError("Zdjęcie przekracza limit 20 megapikseli.")
        source.load()
        image = ImageOps.exif_transpose(source).convert("RGBA")
    protected = _protected_details(image) if method == "smart" else None
    mask = np.asarray(_predict_mask(image), dtype=np.uint16)
    if protected is not None:
        mask[protected] = 255
    original_alpha = np.asarray(image.getchannel("A"), dtype=np.uint16)
    image.putalpha(Image.fromarray(((mask * original_alpha + 127) // 255).astype(np.uint8)))
    image.save(output_path, format="PNG", compress_level=6)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Lokalne usuwanie tła (U²-NetP, CPU)")
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--method", choices=("smart", "ai"), default="smart")
    args = parser.parse_args()
    remove_background(args.input, args.output, method=args.method)
