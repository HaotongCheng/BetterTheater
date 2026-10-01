"""PROTOTYPE — throwaway. Full-frame OCR dump for every local sample, both engines, with timing.
Writes out/ocr_cache.json (gitignored; contains on-screen text incl. UID)."""
import json, time, pathlib
import numpy as np
from PIL import Image
from samples import SAMPLES
from rapidocr_onnxruntime import RapidOCR
import winocr

rapid = RapidOCR()
out = {}
for sid, path in SAMPLES.items():
    im = Image.open(path).convert("RGB")
    t = time.perf_counter(); res, _ = rapid(np.array(im)); tr = time.perf_counter() - t
    t = time.perf_counter(); w = winocr.recognize_pil_sync(im, "zh-Hans-CN"); tw = time.perf_counter() - t
    out[sid] = {
        "size": im.size,
        "rapid": {"sec": tr, "items": [{"box": [[float(x), float(y)] for x, y in b], "text": s, "score": float(c)} for b, s, c in (res or [])]},
        "win": {"sec": tw, "lines": [{"text": l["text"], "words": [{"text": wd["text"], "rect": wd["bounding_rect"]} for wd in l["words"]]} for l in w["lines"]]},
    }
    print(sid, im.size, round(tr, 2), round(tw, 2), flush=True)
pathlib.Path("out").mkdir(exist_ok=True)
json.dump(out, open("out/ocr_cache.json", "w", encoding="utf-8"), ensure_ascii=False)
