from expense_intelligence.config import Settings
from expense_intelligence.ocr.fake import FakeOcrProvider
from expense_intelligence.ocr.textract import TextractOcrProvider
from expense_intelligence.ocr.types import OcrProvider


def make_ocr_provider(settings: Settings) -> OcrProvider:
    if settings.ocr_provider == "textract":
        return TextractOcrProvider(settings.s3_region)
    return FakeOcrProvider()
