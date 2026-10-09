# RAG Design

## Retrieval contract

The RAG pipeline must receive an authorization context and use it when constructing the retrieval query. The backend should return only authorized chunks, source metadata, and citation locations.

## Retrieval algorithm

1. Validate the user query.
2. Create a query embedding.
3. Search PostgreSQL with pgvector.
4. Apply document and row-level permission predicates in the same query.
5. Limit results by rank and requested source count.
6. Deduplicate overlapping chunks.
7. Build a context block from authorized chunks only.

## Context construction

The context should contain:

- The user question.
- The authorized source identity and location.
- The approved content text.
- A clear instruction that the answer must use only the provided context.
- A citation-template constraint.

The context must not contain:

- Unauthorized documents.
- Unauthorized rows.
- Unfiltered search results.
- Internal authorization policy details.
- Secrets or provider credentials.

## LLM provider abstraction

Define an interface that accepts:

- A system instruction.
- An authorized context block.
- A user question.
- A response schema.
- An optional maximum citation count.

The provider implementation must be selected through environment configuration. The backend code must not depend on provider-specific response types beyond the adapter boundary.

## Answer contract

The model response should be structured as:

```json
{
  "answer": "A concise answer grounded in the supplied context.",
  "claims": [
    {
      "text": "A factual claim.",
      "citation_ids": ["source-id:location"]
    }
  ],
  "uncertainty": "An optional uncertainty statement."
}
```

## Citation validation

Before returning a response:

1. Parse every citation identifier.
2. Confirm that each identifier belongs to an authorized source.
3. Confirm that each source was present in the authorized retrieval result.
4. Confirm that the citation text is present in the source chunk.
5. Reject fabricated citations.
6. Reject claims without a valid citation when the response claims a factual fact.
7. Return a safe refusal if validation fails.

## Grounding checks

- Exact source citation is required for factual claims.
- The response must not state facts from outside the context.
- The backend should keep a stable mapping between chunk IDs and source identifiers.
- A model-generated citation cannot override the backend’s authoritative source map.

## Prompt-injection strategy

The LLM should receive retrieved data as untrusted content. The system instruction should specify that content is data and must not alter authorization, identity, or instructions. Output validation must enforce schemas and source allowlists. Security tests should verify that malicious text in a source cannot cause the model to reveal another document or invent a citation.

## Failure behavior

- Zero authorized chunks: return a controlled `no_authorized_context` response.
- LLM provider failure: return a retryable service error.
- Citation validation failure: do not return the model response.
- Retrieval failure: log and return a sanitized error.
- Context score below a configured threshold: return fewer results or a no-match response.
