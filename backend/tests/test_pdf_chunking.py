import unittest

from app.services.pdf.chunker import PDFChunkingError, chunk_pdf_pages


class PDFChunkingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.extraction = {
            "page_count": 2,
            "pages": [
                {
                    "page_number": 1,
                    "text": "First paragraph.\n\nSecond paragraph.",
                    "cleaned_text": "First paragraph.\n\nSecond paragraph.",
                },
                {
                    "page_number": 2,
                    "text": "Third paragraph.\n\nFourth paragraph.",
                    "cleaned_text": "Third paragraph.\n\nFourth paragraph.",
                },
            ],
        }

    def test_chunks_are_deterministic_and_page_local(self) -> None:
        first = chunk_pdf_pages(self.extraction, chunk_size=24, chunk_overlap=5)
        second = chunk_pdf_pages(self.extraction, chunk_size=24, chunk_overlap=5)

        self.assertEqual(first, second)
        self.assertEqual([chunk["chunk_index"] for chunk in first], list(range(len(first))))
        self.assertEqual([chunk["page_number"] for chunk in first], [1, 1, 2, 2])
        self.assertTrue(all(chunk["content"] for chunk in first))
        self.assertTrue(all(chunk["source_locator"] for chunk in first))
        self.assertTrue(all(chunk["metadata"]["source_type"] == "pdf" for chunk in first))
        self.assertTrue(all(chunk["metadata"]["page_number"] == chunk["page_number"] for chunk in first))
        self.assertTrue(all(chunk["metadata"]["chunk_index"] == chunk["chunk_index"] for chunk in first))
        self.assertFalse(any("First paragraph" in chunk["content"] and "Third paragraph" in chunk["content"] for chunk in first))

    def test_overlap_is_controlled_and_does_not_create_empty_chunks(self) -> None:
        chunks = chunk_pdf_pages(self.extraction, chunk_size=30, chunk_overlap=8)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(chunk["content"] for chunk in chunks))
        self.assertTrue(chunks[1]["content"].startswith(chunks[0]["content"][-8:]))

    def test_empty_pages_produce_no_chunks(self) -> None:
        extraction = {
            "page_count": 2,
            "pages": [
                {"page_number": 1, "text": "", "cleaned_text": ""},
                {"page_number": 2, "text": "", "cleaned_text": ""},
            ],
        }

        self.assertEqual(chunk_pdf_pages(extraction), [])

    def test_small_content_remains_one_chunk(self) -> None:
        extraction = {
            "page_count": 1,
            "pages": [{"page_number": 1, "text": "One paragraph", "cleaned_text": "One paragraph"}],
        }

        chunks = chunk_pdf_pages(extraction, chunk_size=100, chunk_overlap=0)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]["content"], "One paragraph")

    def test_invalid_configuration_is_rejected(self) -> None:
        with self.assertRaisesRegex(PDFChunkingError, "Chunk size"):
            chunk_pdf_pages(self.extraction, chunk_size=0)

        with self.assertRaisesRegex(PDFChunkingError, "Chunk overlap"):
            chunk_pdf_pages(self.extraction, chunk_size=10, chunk_overlap=10)

        with self.assertRaisesRegex(PDFChunkingError, "Chunk overlap"):
            chunk_pdf_pages(self.extraction, chunk_size=10, chunk_overlap=11)


if __name__ == "__main__":
    unittest.main()
