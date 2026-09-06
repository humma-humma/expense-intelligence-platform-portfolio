import json
from importlib.resources import files

from expense_intelligence.ocr.types import OcrExtraction


class FakeOcrProvider:
    def extract(self, image_bytes: bytes) -> OcrExtraction:
        del image_bytes
        fixture_path = files("expense_intelligence.ocr").joinpath("fixtures/fake_receipt.json")
        raw: dict[str, object] = json.loads(fixture_path.read_text(encoding="utf-8"))
        return OcrExtraction.model_validate(
            {
                "provider": "fake",
                "provider_version": "1",
                "receipt": raw,
                "raw": raw,
            }
        )
