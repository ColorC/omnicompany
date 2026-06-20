"""visual_diff.py — 截图视觉对比工具.

提供 SSIM (Structural Similarity) + 简单像素差 + 直方图相似度三种度量,
用于 invariants verify_method=pixel_diff_threshold 调度.

设计:
- 不接 vision LLM (那是另一档).
- Pillow + numpy 实现, 不依赖 scikit-image (避免重型依赖).
- SSIM 简化版: 滑窗 8x8 求 mean/std/cov, 公式参 Wang et al. 2004.
- 输入两张 PNG/JPG; 自动 resize 对齐到较小那张 + 灰度化.
- 输出: { ssim, pixel_diff_mean, hist_similarity, verdict, reason }

跑法 (CLI):
  python visual_diff.py <actual.png> <baseline.png>
  python visual_diff.py <actual.png> <baseline.png> --threshold 0.75 --json

库用 (Python):
  from visual_diff import compare
  result = compare("actual.png", "baseline.png", threshold=0.75)
  if result["verdict"] == "pass": ...
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Any

import numpy as np
from PIL import Image


def _load_grayscale(path: str | Path, target_size: tuple[int, int] | None = None) -> np.ndarray:
    """加载图片, 转灰度, 可选 resize."""
    img = Image.open(path).convert("L")
    if target_size:
        img = img.resize(target_size, Image.LANCZOS)
    return np.asarray(img, dtype=np.float64)


def _ssim_simple(a: np.ndarray, b: np.ndarray, window: int = 8) -> float:
    """简化 SSIM. window 默认 8x8 滑窗.

    参: Wang, Bovik, Sheikh, Simoncelli (2004) IEEE TIP.
    SSIM = (2μₐμᵦ + C1)(2σₐᵦ + C2) / ((μₐ²+μᵦ²+C1)(σₐ²+σᵦ²+C2))
    """
    h, w = a.shape
    if h < window or w < window:
        return float("nan")

    L = 255.0  # 灰度动态范围
    C1 = (0.01 * L) ** 2
    C2 = (0.03 * L) ** 2

    # 不重叠 8x8 块求 mean/std/cov
    n_blocks_h = h // window
    n_blocks_w = w // window
    a = a[: n_blocks_h * window, : n_blocks_w * window]
    b = b[: n_blocks_h * window, : n_blocks_w * window]
    a_blocks = a.reshape(n_blocks_h, window, n_blocks_w, window).swapaxes(1, 2)
    b_blocks = b.reshape(n_blocks_h, window, n_blocks_w, window).swapaxes(1, 2)
    a_blocks = a_blocks.reshape(n_blocks_h * n_blocks_w, window * window)
    b_blocks = b_blocks.reshape(n_blocks_h * n_blocks_w, window * window)

    mu_a = a_blocks.mean(axis=1)
    mu_b = b_blocks.mean(axis=1)
    var_a = a_blocks.var(axis=1)
    var_b = b_blocks.var(axis=1)
    cov_ab = ((a_blocks - mu_a[:, None]) * (b_blocks - mu_b[:, None])).mean(axis=1)

    num = (2 * mu_a * mu_b + C1) * (2 * cov_ab + C2)
    den = (mu_a ** 2 + mu_b ** 2 + C1) * (var_a + var_b + C2)
    ssim_per_block = num / den
    return float(ssim_per_block.mean())


def _pixel_diff_mean(a: np.ndarray, b: np.ndarray) -> float:
    """绝对像素差均值, 归一化到 [0, 1]."""
    return float(np.abs(a - b).mean() / 255.0)


def _hist_similarity(a: np.ndarray, b: np.ndarray, bins: int = 32) -> float:
    """直方图交集相似度 [0, 1], 1 = 完全一致."""
    h_a, _ = np.histogram(a, bins=bins, range=(0, 255), density=True)
    h_b, _ = np.histogram(b, bins=bins, range=(0, 255), density=True)
    return float(np.minimum(h_a, h_b).sum() / max(h_a.sum(), 1e-9))


def compare(
    actual: str | Path,
    baseline: str | Path,
    threshold: float = 0.75,
    threshold_partial: float = 0.6,
) -> Dict[str, Any]:
    """对比两张图. 返回 ssim/pixel_diff/hist + verdict.

    threshold: SSIM ≥ 这个值给 pass. 默认 0.75.
    threshold_partial: ≥ 这个值给 partial (低于 threshold 但还能看). 默认 0.6.
    """
    actual_p = Path(actual)
    baseline_p = Path(baseline)
    if not actual_p.exists():
        return {"error": f"actual not found: {actual_p}"}
    if not baseline_p.exists():
        return {"error": f"baseline not found: {baseline_p}"}

    img_a_raw = Image.open(actual_p)
    img_b_raw = Image.open(baseline_p)
    # 对齐到较小尺寸的 max(w,h), 等比缩放
    target_w = min(img_a_raw.width, img_b_raw.width, 480)
    target_h = min(img_a_raw.height, img_b_raw.height, 1040)

    a = _load_grayscale(actual_p, (target_w, target_h))
    b = _load_grayscale(baseline_p, (target_w, target_h))

    ssim = _ssim_simple(a, b)
    pdiff = _pixel_diff_mean(a, b)
    hist = _hist_similarity(a, b)

    if ssim >= threshold:
        verdict = "pass"
        reason = f"SSIM {ssim:.3f} ≥ threshold {threshold}"
    elif ssim >= threshold_partial:
        verdict = "partial"
        reason = f"SSIM {ssim:.3f} 在 [{threshold_partial}, {threshold}) 区间"
    else:
        verdict = "fail"
        reason = f"SSIM {ssim:.3f} < threshold_partial {threshold_partial}"

    return {
        "actual": str(actual_p),
        "baseline": str(baseline_p),
        "compared_size": [target_w, target_h],
        "ssim": ssim,
        "pixel_diff_mean": pdiff,
        "hist_similarity": hist,
        "verdict": verdict,
        "reason": reason,
        "thresholds": {"pass": threshold, "partial": threshold_partial},
    }


def main():
    p = argparse.ArgumentParser(description="Visual diff (SSIM + pixel + hist).")
    p.add_argument("actual", help="实物截图 path")
    p.add_argument("baseline", help="baseline 截图 path")
    p.add_argument("--threshold", type=float, default=0.75)
    p.add_argument("--threshold-partial", type=float, default=0.6)
    p.add_argument("--json", action="store_true", help="输出 JSON")
    args = p.parse_args()

    result = compare(args.actual, args.baseline, args.threshold, args.threshold_partial)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if "error" in result:
            print(f"ERROR: {result['error']}", file=sys.stderr)
            sys.exit(2)
        print(f"actual:   {result['actual']}")
        print(f"baseline: {result['baseline']}")
        print(f"size:     {result['compared_size']}")
        print(f"SSIM:     {result['ssim']:.3f}")
        print(f"pixDiff:  {result['pixel_diff_mean']:.3f}")
        print(f"hist:     {result['hist_similarity']:.3f}")
        print(f"verdict:  {result['verdict']}  ({result['reason']})")


if __name__ == "__main__":
    main()
