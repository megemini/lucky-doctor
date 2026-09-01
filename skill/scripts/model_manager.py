"""
Model manager for lazy loading OpenVINO models.
Only loads the OCR model needed in this SKILL flow.
"""

import gc
import logging
import time
from pathlib import Path

logger = logging.getLogger("lucky_doctor")


class ModelManager:
    """Lazy model manager that loads OCR and TTS models on demand."""

    def __init__(self, ocr_model_dir, tts_model_dir=None, device="AUTO"):
        self.ocr_model_dir = str(ocr_model_dir)
        self.tts_model_dir = str(tts_model_dir) if tts_model_dir else None
        self.device = device

        self._ocr_model = None
        self._tts_model = None
        self._ov_core = None

    def _get_ov_core(self):
        if self._ov_core is None:
            import openvino as ov
            self._ov_core = ov.Core()
        return self._ov_core

    def get_ocr_model(self):
        if self._ocr_model is None:
            logger.info("Loading OCR model (PaddleOCR-VL)...")
            start = time.perf_counter()
            import sys
            lib_dir = str(Path(__file__).resolve().parent.parent / "lib")
            if lib_dir not in sys.path:
                sys.path.insert(0, lib_dir)
            from ov_paddleocr_vl import OVPaddleOCRVLForCausalLM
            core = self._get_ov_core()
            self._ocr_model = OVPaddleOCRVLForCausalLM(
                core=core,
                ov_model_path=self.ocr_model_dir,
                device=self.device,
                llm_int4_compress=False,
                llm_int8_compress=True,
                vision_int8_quant=False,
                llm_int8_quant=True,
                llm_infer_list=[],
                vision_infer=[],
            )
            logger.info("OCR model loaded in %.2fs", time.perf_counter() - start)
        return self._ocr_model

    def get_tts_model(self):
        if self.tts_model_dir is None:
            raise RuntimeError("TTS model dir not provided; cannot load TTS model")
        if self._tts_model is None:
            logger.info("Loading TTS model (Qwen3-TTS)...")
            start = time.perf_counter()
            import sys
            lib_dir = str(Path(__file__).resolve().parent.parent / "lib")
            if lib_dir not in sys.path:
                sys.path.insert(0, lib_dir)
            from qwen_3_tts_helper import OVQwen3TTSModel
            self._tts_model = OVQwen3TTSModel.from_pretrained(
                model_dir=self.tts_model_dir,
                device=self.device,
            )
            logger.info("TTS model loaded in %.2fs", time.perf_counter() - start)
        return self._tts_model

    def release_ocr(self):
        if self._ocr_model is not None:
            del self._ocr_model
            self._ocr_model = None
            gc.collect()

    def release_tts(self):
        if self._tts_model is not None:
            del self._tts_model
            self._tts_model = None
            gc.collect()

    def release_all(self):
        self.release_ocr()
        self.release_tts()
