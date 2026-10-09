"""Part 6.1 query validation: RagQuery is the single gate before secure retrieval."""

import unittest

from pydantic import ValidationError

from app.schemas.embeddings import VectorSearchRequest
from app.schemas.rag import DEFAULT_TOP_K, MAX_QUERY_LENGTH, RagQuery
from app.services.vector_search import VectorSearchService


class RagQueryValidationTests(unittest.TestCase):
    def assertRejected(self, error_type: str, **fields: object) -> None:
        with self.assertRaises(ValidationError) as caught:
            RagQuery(**fields)
        self.assertIn(error_type, {error["type"] for error in caught.exception.errors()})

    def test_valid_query_with_default_top_k(self) -> None:
        query = RagQuery(query="What is the Finance department budget?")
        self.assertEqual(query.query, "What is the Finance department budget?")
        self.assertEqual(query.top_k, DEFAULT_TOP_K)

    def test_surrounding_whitespace_is_trimmed_and_nothing_else_changes(self) -> None:
        query = RagQuery(query="  \n\t What is  the MFA   policy?\n ")
        self.assertEqual(query.query, "What is  the MFA   policy?")

    def test_empty_and_whitespace_only_queries_are_rejected(self) -> None:
        self.assertRejected("string_too_short", query="")
        self.assertRejected("string_too_short", query="   \n\t  ")

    def test_query_length_limit(self) -> None:
        self.assertEqual(len(RagQuery(query="x" * MAX_QUERY_LENGTH).query), MAX_QUERY_LENGTH)
        # Trimming happens before the length check.
        self.assertEqual(len(RagQuery(query=f"  {'x' * MAX_QUERY_LENGTH}  ").query), MAX_QUERY_LENGTH)
        self.assertRejected("string_too_long", query="x" * (MAX_QUERY_LENGTH + 1))

    def test_query_must_be_a_string(self) -> None:
        self.assertRejected("string_type", query=123)
        self.assertRejected("string_type", query=None)
        self.assertRejected("string_type", query=["budget"])
        self.assertRejected("missing", top_k=5)

    def test_valid_top_k_values(self) -> None:
        for top_k in (1, 5, VectorSearchService.MAX_TOP_K):
            with self.subTest(top_k=top_k):
                self.assertEqual(RagQuery(query="budget", top_k=top_k).top_k, top_k)

    def test_invalid_top_k_values(self) -> None:
        self.assertRejected("greater_than_equal", query="budget", top_k=0)
        self.assertRejected("greater_than_equal", query="budget", top_k=-3)
        self.assertRejected("less_than_equal", query="budget", top_k=VectorSearchService.MAX_TOP_K + 1)
        self.assertRejected("less_than_equal", query="budget", top_k=1_000)
        # Strict integers: no coercion from text, floats or booleans.
        for value in ("5", 5.0, 2.5, True, None):
            with self.subTest(value=value):
                self.assertRejected("int_type", query="budget", top_k=value)

    def test_top_k_bounds_match_existing_vector_search(self) -> None:
        def bounds(model: type) -> tuple[int, int]:
            metadata = model.model_fields["top_k"].metadata
            return (
                next(item.ge for item in metadata if hasattr(item, "ge")),
                next(item.le for item in metadata if hasattr(item, "le")),
            )

        self.assertEqual(bounds(RagQuery), (1, VectorSearchService.MAX_TOP_K))
        self.assertEqual(bounds(RagQuery), bounds(VectorSearchRequest))

    def test_identity_fields_cannot_be_supplied(self) -> None:
        for field in ("user_id", "role", "roles", "department", "permissions", "email"):
            with self.subTest(field=field):
                self.assertRejected("extra_forbidden", query="budget", **{field: "SUPER_ADMIN"})

    def test_json_input_is_validated_the_same_way(self) -> None:
        self.assertEqual(RagQuery.model_validate_json('{"query": " budget ", "top_k": 3}').query, "budget")
        for body in ('{"query": "   "}', '{"query": "budget", "top_k": 21}', '{"query": "budget", "top_k": "3"}',
                     '{"query": "budget", "user_id": "x"}'):
            with self.subTest(body=body), self.assertRaises(ValidationError):
                RagQuery.model_validate_json(body)

    def test_validated_query_is_immutable(self) -> None:
        query = RagQuery(query="budget")
        with self.assertRaises(ValidationError):
            query.query = "something else"


if __name__ == "__main__":
    unittest.main()
