from __future__ import annotations

import cv2
import numpy as np

PORTRAIT_W = 0.1078
PORTRAIT_TOP = 0.004
SLOT_LEFT = [-0.695, -0.581, -0.468, -0.354, -0.238]
SLOT_RIGHT = [0.124, 0.240, 0.354, 0.469, 0.583]
STRIP_H = 0.115
CALIBRATION_SCALES = [1.0] + [round(1 + s * i * 0.04, 2) for i in range(1, 9) for s in (-1, 1)]
STANDARD_ASPECT = 16 / 9


def is_standard(w: int, h: int) -> bool:
    return abs(w / h - STANDARD_ASPECT) < 0.03
MARGIN = 0.016
SCALE_TRIES = (1.0, 0.96, 1.04)

WORK_PW = 64
CROP = (0.18, 0.82, 0.08, 0.80)
V_COLOUR = 0.60
V_EDGE = 0.40


def imread(path) -> np.ndarray | None:
    try:
        data = np.fromfile(str(path), dtype=np.uint8)
        return cv2.imdecode(data, cv2.IMREAD_COLOR)
    except Exception:
        return None


class Detector:
    V_W, V_H, V_PAD = 64, 40, 5

    def __init__(self, heroes: list[dict], img_path_fn):
        self.src = {}
        for h in heroes:
            img = imread(img_path_fn(h))
            if img is not None:
                self.src[h["id"]] = img
        self._tmpl_cache: dict[int, dict[int, np.ndarray]] = {}
        self._verify_cache: dict[int, tuple] = {}

    def warm(self):
        for sc in SCALE_TRIES:
            self._templates(int(round(WORK_PW * sc)))
        for hid in self.src:
            self._verify_tmpl(hid)


    def _templates(self, w: int) -> dict[int, np.ndarray]:
        t = self._tmpl_cache.get(w)
        if t is None:
            t = {}
            for hid, img in self.src.items():
                h = max(8, int(round(w * img.shape[0] / img.shape[1])))
                small = cv2.resize(img, (w, h), interpolation=cv2.INTER_AREA)
                t[hid] = small[int(h * CROP[2]):int(h * CROP[3]), int(w * CROP[0]):int(w * CROP[1])]
            self._tmpl_cache[w] = t
        return t


    @staticmethod
    def _edges(img: np.ndarray) -> np.ndarray:
        g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
        return cv2.magnitude(cv2.Sobel(g, cv2.CV_32F, 1, 0), cv2.Sobel(g, cv2.CV_32F, 0, 1))

    def _verify_tmpl(self, hid: int):
        t = self._verify_cache.get(hid)
        if t is None:
            img = self.src[hid]
            h, w = img.shape[:2]
            crop = img[int(h * CROP[2]):int(h * CROP[3]), int(w * CROP[0]):int(w * CROP[1])]
            big = cv2.resize(crop, (self.V_W, self.V_H), interpolation=cv2.INTER_AREA)
            p = self.V_PAD
            t = (big[p:-p, p:-p], self._edges(big)[p:-p, p:-p])
            self._verify_cache[hid] = t
        return t

    def verify(self, frame: np.ndarray, box, hid: int) -> tuple[float, float]:
        x, y, w, h = box
        x, y = max(0, x), max(0, y)
        patch = frame[y:y + h, x:x + w]
        if patch.shape[0] < 6 or patch.shape[1] < 10:
            return 0.0, 0.0
        patch = cv2.resize(patch, (self.V_W, self.V_H), interpolation=cv2.INTER_AREA)
        col_t, edge_t = self._verify_tmpl(hid)
        c = float(cv2.matchTemplate(patch, col_t, cv2.TM_CCOEFF_NORMED).max())
        e = float(cv2.matchTemplate(self._edges(patch), edge_t, cv2.TM_CCOEFF_NORMED).max())
        return c, e


    def calibrate(self, frame: np.ndarray, win_h: int, thr: float = 0.7):
        best = None
        for k in CALIBRATION_SCALES:
            r = self.detect(frame, win_h, thr, k, tries=(1.0,))
            n = sum(1 for s in r["slots"] if s)
            if not n:
                continue
            score = (n, sum(b[5] for b in r["boxes"]))
            if best is None or score > best[0]:
                best = (score, k, r)
        return (best[1], best[2]) if best else None

    def detect(self, frame: np.ndarray, win_h: int, thr: float = 0.7, k: float = 1.0,
               tries=SCALE_TRIES) -> dict:
        f = WORK_PW / (PORTRAIT_W * k * win_h)
        work = cv2.resize(frame, (max(8, int(round(frame.shape[1] * f))),
                                  max(8, int(round(frame.shape[0] * f)))), interpolation=cv2.INTER_AREA)
        hw_ = work.shape[1] / 2
        unit = WORK_PW / PORTRAIT_W
        m = MARGIN * unit
        ph = WORK_PW * 144 / 256
        slots, boxes = [], []
        for left in SLOT_LEFT + SLOT_RIGHT:
            x0 = int(max(0, hw_ + left * unit - m))
            x1 = int(min(work.shape[1], hw_ + left * unit + WORK_PW + m))
            y1 = int(min(work.shape[0], PORTRAIT_TOP * unit + ph + m))
            region = work[0:y1, x0:x1]
            best = None
            for sc in tries:
                if best and best[0] >= max(thr, 0.8):
                    break
                for hid, tmpl in self._templates(int(round(WORK_PW * sc))).items():
                    if tmpl.shape[0] > region.shape[0] or tmpl.shape[1] > region.shape[1]:
                        continue
                    res = cv2.matchTemplate(region, tmpl, cv2.TM_CCOEFF_NORMED)
                    _, val, _, loc = cv2.minMaxLoc(res)
                    if best is None or val > best[0]:
                        best = (float(val), hid, x0 + loc[0], loc[1], tmpl.shape[1], tmpl.shape[0])
            found = None
            if best and best[0] >= thr:
                box = (int(best[2] / f), int(best[3] / f), int(round(best[4] / f)), int(round(best[5] / f)))
                c, e = self.verify(frame, box, best[1])
                if c >= V_COLOUR and e >= V_EDGE:
                    found = best[1]
                    boxes.append((*box, best[1], best[0]))
            slots.append(found)
        return {"left": [h for h in slots[:5] if h], "right": [h for h in slots[5:] if h],
                "boxes": boxes, "slots": slots}
