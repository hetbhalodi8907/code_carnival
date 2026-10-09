import unittest
from uuid import uuid4
from pathlib import Path
from unittest.mock import patch

from fitz import open

from app.services.pdf.cleaner import clean_text
from app.services.pdf.extractor import extract_pdf_pages
from app.services.pdf.validator import PDFValidationError, validate_pdf_upload
from auth_fixtures import clear_current_user_override, override_current_user, principal
from support import call_app


PDF_FIXTURE = Path(__file__).parent / "fixtures" / "synthetic.pdf"


def create_synthetic_pdf(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    document = open()
    page_one = document.new_page(width=612, height=792)
    page_one.draw_rect([36, 36, 576, 756])
    page_one.insert_text(
        (72, 72),
        "Page 1\nPDF ingestion test.\nA second paragraph with  extra whitespace.",
        fontsize=14,
    )
    page_two = document.new_page(width=612, height=792)
    page_two.insert_text(
        (72, 72),
        "Page 2\nSecond page extraction test.\n",
        fontsize=14,
    )
    document.save(path)
    document.close()


class PDFValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        create_synthetic_pdf(PDF_FIXTURE)

    def test_valid_pdf_is_accepted(self) -> None:
        content = PDF_FIXTURE.read_bytes()
        validate_pdf_upload(PDF_FIXTURE.name, "application/pdf", content)

    def test_invalid_extension_is_rejected(self) -> None:
        with self.assertRaisesRegex(PDFValidationError, "Only PDF files"):
            validate_pdf_upload("notes.txt", "text/plain", b"not a pdf")

    def test_fake_pdf_is_rejected(self) -> None:
        with self.assertRaisesRegex(PDFValidationError, "not a valid PDF"):
            validate_pdf_upload("fake.pdf", "application/pdf", b"not a pdf")

    def test_empty_file_is_rejected(self) -> None:
        with self.assertRaisesRegex(PDFValidationError, "empty"):
            validate_pdf_upload("empty.pdf", "application/pdf", b"")

    def test_file_size_limit_is_enforced(self) -> None:
        with patch("app.services.pdf.validator.settings.max_pdf_size_mb", 0):
            with self.assertRaisesRegex(PDFValidationError, "no larger than 0 MB"):
                validate_pdf_upload("large.pdf", "application/pdf", b"x")


class PDFExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        create_synthetic_pdf(PDF_FIXTURE)

    def test_page_wise_extraction_preserves_page_numbers(self) -> None:
        extraction = extract_pdf_pages(PDF_FIXTURE.read_bytes())

        self.assertEqual(extraction["page_count"], 2)
        self.assertTrue(extraction["has_extractable_text"])
        self.assertEqual([page["page_number"] for page in extraction["pages"]], [1, 2])
        self.assertIn("Page 1", extraction["pages"][0]["text"])
        self.assertIn("Page 2", extraction["pages"][1]["text"])

    def test_cleaning_normalizes_whitespace_without_rewriting_content(self) -> None:
        cleaned = clean_text("First line\r\n\r\nSecond\t  line.\n\n")
        self.assertEqual(cleaned, "First line\n\nSecond line.")
        self.assertIn("Second", cleaned)
        self.assertNotIn("\t", cleaned)

    def test_empty_text_page_is_reported_without_ocr_claim(self) -> None:
        empty_pdf = PDF_FIXTURE.with_name("empty-text.pdf")
        document = open()
        document.new_page(width=612, height=792)
        document.save(empty_pdf)
        document.close()

        extraction = extract_pdf_pages(empty_pdf.read_bytes())
        self.assertEqual(extraction["page_count"], 1)
        self.assertFalse(extraction["has_extractable_text"])
        self.assertEqual(extraction["pages"][0]["text"], "")
        self.assertEqual(extraction["pages"][0]["cleaned_text"], "")


class PDFPreviewApiTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        create_synthetic_pdf(PDF_FIXTURE)

    def setUp(self) -> None:
        # Preview requires documents:write; enforcement is tested in test_authorization.py.
        override_current_user(principal(uuid4(), "documents:write"))

    def tearDown(self) -> None:
        clear_current_user_override()

    async def test_preview_endpoint_returns_structured_page_text(self) -> None:
        content = PDF_FIXTURE.read_bytes()
        boundary = "----pdf-preview-test"
        body = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="file"; filename="synthetic.pdf"\r\n'
            "Content-Type: application/pdf\r\n\r\n"
        ).encode() + content + f"\r\n--{boundary}--\r\n".encode()

        status, headers, response = await call_app(
            "POST",
            "/api/v1/documents/preview",
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            body=body,
        )

        self.assertEqual(status, 200)
        self.assertIn("x-request-id", headers)
        self.assertIn('"filename":"synthetic.pdf"', response["body"])
        self.assertIn('"page_count":2', response["body"])
        self.assertIn('"page_number":1', response["body"])
        self.assertIn('"page_number":2', response["body"])
        self.assertNotIn("/tmp", response["body"])

    async def test_preview_rejects_invalid_file_without_exposing_details(self) -> None:
        boundary = "----pdf-invalid-test"
        body = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="file"; filename="fake.pdf"\r\n'
            "Content-Type: application/pdf\r\n\r\n"
            "not a pdf\r\n"
            f"--{boundary}--\r\n"
        ).encode()

        status, headers, response = await call_app(
            "POST",
            "/api/v1/documents/preview",
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            body=body,
        )

        self.assertEqual(status, 400)
        self.assertIn("x-request-id", headers)
        self.assertIn("not a valid PDF", response["body"])
        self.assertNotIn("traceback", response["body"].lower())

    async def test_preview_rejects_wrong_extension(self) -> None:
        boundary = "----pdf-extension-test"
        body = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="file"; filename="notes.txt"\r\n'
            "Content-Type: text/plain\r\n\r\n"
            "not a pdf\r\n"
            f"--{boundary}--\r\n"
        ).encode()

        status, _, response = await call_app(
            "POST",
            "/api/v1/documents/preview",
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            body=body,
        )

        self.assertEqual(status, 400)
        self.assertIn("Only PDF files", response["body"])


if __name__ == "__main__":
    create_synthetic_pdf(PDF_FIXTURE.parent / "synthetic.pdf")
    unittest.main()
