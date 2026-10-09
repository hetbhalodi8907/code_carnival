# Security Model

## Security-flow diagram

```text
Authenticated User
        |
        | request + user identity
        v
Authorization context
        |
        +--> role permissions
        +--> document permissions
        +--> row permissions
        |
        v
Query embedding (no source data returned yet)
        |
        v
Permission-aware PostgreSQL vector query
        |
        +--> unauthorized document/row: rejected at SQL boundary
        +--> authorized document/row: returned as candidate
        |
        v
Authorized context only
        |
        v
LLM prompt / tool boundary
        |
        v
Model response
        |
        v
Citation validator
        |
        +--> cited source absent from authorized context: reject
        +--> cited source present: retain
        |
        v
Validated response to user
```

## Authorization boundary

The authorization decision must occur inside the retrieval operation. The backend must not first retrieve all matching chunks, then filter them in application code before sending text to the LLM. The retrieval query must include the effective permission predicates, and the result set must be the authorized set.

## Permission rules

### Role-based controls

- Roles define baseline permissions.
- Roles can grant access to documents or source classes.
- A user may have multiple roles.
- Role permissions are resolved into one effective permission set per request.

### Document-level controls

- Each document has an owner and one or more access policy entries.
- A user must have an explicit grant or an inherited role grant.
- Document access is checked before any document chunks are returned.
- Deleted or inactive documents must not be searchable.

### Row-level controls

- Each structured record has an owner or tenant scope.
- Row access is checked using a database predicate.
- A user can receive a row only when its row-level policy matches.
- Image and PDF sources should use the same document-level model.

## Authorization data flow

```text
User identity
     |
     v
Role assignments
     |
     v
Document ACLs
     |
     v
Row ACLs
     |
     v
Effective authorization context
     |
     v
SQL predicates on retrieval
```

## Prompt-injection controls

- Treat retrieved content as untrusted data, not instructions.
- Keep retrieved content in a clearly isolated context section.
- Do not permit the model to interpret content as policy or identity data.
- Use strict output schemas and validate citations.
- Use allowlists for permitted response fields.
- Never expose internal authorization rules or secrets to the model.
- Test prompt-injection payloads placed in PDFs, images, and database rows.

## Citation controls

- Each citation uses a stable source identifier.
- Every cited source must be present in the authorized retrieval result.
- Citation identifiers must not be invented by the model.
- Unsupported or ambiguous claims must be rejected or labeled uncertain.
- The backend must store the citation contract and validate each response.

## Data handling

- Store secrets in environment variables or a secret manager.
- Never commit `.env` files or credentials.
- Encrypt data at rest where the deployment platform supports it.
- Use least-privilege database roles.
- Log authorization outcomes with a request identifier but avoid logging sensitive content.
- Restrict application database access to the minimum required tables.

## Security test cases

- A user without document permission asks about its content.
- A user with document access but without row access requests a structured row.
- A document contains prompt-injection text attempting to reveal another source.
- A model invents a citation that was not retrieved.
- A removed or deleted document is queried.
- A source contains malformed or malicious text and OCR output.
- A user changes client-side authorization state.
- A model response includes a source outside the authorized set.

## Incident and audit requirements

- Record authentication failures, authorization denials, retrieval failures, citation failures, and policy changes.
- Correlate events with a request and actor identifier.
- Alert on repeated authorization failures and citation-validation failures.
- Preserve audit records without persisting full user prompts or complete sensitive content unless explicitly approved.
