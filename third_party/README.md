# Local background removal

U²-NetP model, U-2-Net by Xuebin Qin et al. (Apache License 2.0, full text in U2NET-LICENSE.txt).

- Original project: https://github.com/xuebinqin/U-2-Net
- ONNX distribution: https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2netp.onnx
- Preprocessing reference: https://github.com/danielgatis/rembg/blob/main/rembg/sessions/u2netp.py
- Downloaded 2026-09-21, 4,574,861 bytes (verify local size).
- SHA256: `309c8469258dda742793dce0ebea8e6dd393174f89934733ecc8b14c76f4ddd8`
- Upstream MD5: `8e83ca70e441ab06c318d82300c84806`

The app loads only this verified model from disk. It does not download models or send user images to an external service. Inference is approximate; the user reviews the mask and can erase or restore its edges. Original RGB pixels are retained.
