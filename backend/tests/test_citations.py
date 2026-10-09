"""Part 7: citation normalization and validation against the retrieved sources."""

import unittest
from uuid import UUID, uuid4

from app.services.llm.provider import LLMResponse
from app.services.rag.citations import UNKNOWN_REFERENCE, validate_citations
from app.services.rag.generation import AnswerGenerator, build_generation_messages
from test_rag_generation import FINANCE_RESULTS, FakeLLMProvider, build_context, make_user, QUESTION
from app.schemas.rag import RagQuery


class CitationValidationTests(unittest.TestCase):
    def check(self, answer: str, valid=(1, 2, 3), ids=()):
        return validate_citations(answer, valid, ids)

    def test_every_supported_marker_format_is_normalized_to_ascii_brackets(self) -> None:
        for raw in ("[S1]", "【S1】", "［S1］", "[ S1 ]", "[s1]", "[S 1]", "【 S1 】"):
            with self.subTest(raw=raw):
                result = self.check(f"Budget is INR 1.5 crore {raw}.")
                self.assertEqual(result.text, "Budget is INR 1.5 crore [S1].")
                self.assertEqual((result.cited, result.rejected, result.check), ((1,), (), "passed"))

    def test_grouped_markers_are_split_and_deduplicated_in_order(self) -> None:
        result = self.check("A [S2, S1] and 【S3；】 and [S1;S3] and [S2,3]")
        self.assertEqual(result.cited, (2, 1, 3))
        self.assertEqual(result.text, "A [S2][S1] and 【S3；】 and [S1][S3] and [S2][S3]")

    def test_unknown_source_numbers_are_removed_and_reported(self) -> None:
        result = self.check("Real [S1], fake [S9] and 【S7】, mixed [S2, S8].")
        self.assertEqual(result.text, "Real [S1], fake and, mixed [S2].")
        self.assertEqual(result.cited, (1, 2))
        self.assertEqual(result.rejected, (9, 7, 8))
        self.assertEqual(result.check, "partial")

    def test_an_answer_with_no_valid_citation_is_marked_uncited(self) -> None:
        for answer in ("No markers at all.", "Only fake 【S5】."):
            with self.subTest(answer=answer):
                self.assertEqual(self.check(answer).check, "none")
                self.assertEqual(self.check(answer).cited, ())

    def test_fabricated_identifiers_are_replaced_but_real_ones_survive(self) -> None:
        real, fake = uuid4(), "11111111-1111-4111-8111-111111111111"
        result = self.check(f"Real {real}, fake {fake} and {fake.upper()} [S1].", ids=[real])
        self.assertIn(str(real), result.text)
        self.assertNotIn(fake, result.text.lower())
        self.assertEqual(result.text.count(UNKNOWN_REFERENCE), 2)
        self.assertEqual((result.scrubbed_identifiers, result.check), (2, "partial"))

    def test_prose_that_only_looks_like_a_marker_is_left_alone(self) -> None:
        text = "Plan S1 (phase two), section S3 and the [Sx] tag stay as written."
        self.assertEqual(self.check(text).text, text)


class CitationInGenerationTests(unittest.IsolatedAsyncioTestCase):
    async def test_full_width_brackets_from_the_model_become_valid_citations(self) -> None:
        user = make_user()
        context = await build_context(FINANCE_RESULTS, user)
        provider = FakeLLMProvider(LLMResponse("Budget is INR 1.5 crore【S1】, reviewed quarterly【S2】.", "m", "stop", 1, 1))
        result = await AnswerGenerator(provider).generate(RagQuery(query=QUESTION), context, user=user)

        self.assertEqual(result.answer, "Budget is INR 1.5 crore[S1], reviewed quarterly[S2].")
        self.assertEqual((result.unverified_source_numbers, result.rejected_source_numbers), ((1, 2), ()))
        self.assertEqual(result.citation_check, "passed")

    async def test_prompt_demands_ascii_brackets_and_only_shown_numbers(self) -> None:
        system = build_generation_messages(RagQuery(query=QUESTION), await build_context(FINANCE_RESULTS, make_user()))[0].content
        flat = " ".join(system.split())
        for rule in ("plain ASCII square brackets", "using only the source numbers shown", "Never cite a number that is not shown"):
            self.assertIn(rule, flat)
        self.assertIn("scanned images read by OCR", system)


if __name__ == "__main__":
    unittest.main()
