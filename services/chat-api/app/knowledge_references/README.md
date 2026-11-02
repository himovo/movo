# Knowledge material references

The chat composer accepts `@` followed by a document or directory name. Users can search personal knowledge (owned or actively shared) and organization knowledge, select multiple materials, browse directories, and remove selected references. Selection is independent of learning and parsing status. Authorized original files can be parsed on demand when the Agent reads them.

References are structured message fields, not paths inferred from prompt text. Search uses the authenticated tenant and user. Before admitting a turn, the server resolves each reference again and records its canonical name and document version. A maximum of 20 references is accepted per message.

The Agent receives the references as input materials. It chooses whether to browse, read ordered document text, retrieve facts, or use other capabilities according to the request. No summary workflow or RAG mode is forced. Ordered reads are paginated; the Agent must follow the returned cursor before claiming to have read the entire document.

## Authorization

- Personal materials require ownership or an active share grant.
- Organization search uses the product knowledge-access policy. AskAI batches the existing document, directory-ancestor, and root policy rules; it uses the same department, position-role, and employee audience evaluator as ordinary knowledge access.
- A directory is listed only if at least one accessible document exists below it. Browsing returns accessible documents only.
- Sending a reference revalidates access. Every document read revalidates access again. Changing permissions after selection therefore prevents subsequent unauthorized reads.
- Referenced document version changes are rejected before reading chunks; clients cannot override the canonical version.
- Hiding the personal knowledge management entry does not grant or revoke document access.

## Modules

MOVO owns the composer components, reference API, admission, browsing contract, and ordered document reader. AskAI owns enterprise audience filtering. DSH sources are unchanged.

## Validation and scope

Unit coverage includes tenant separation, hidden document and directory filtering, personal grants, permission revocation, forged metadata, version changes, and pagination through a fully denied page. Frontend coverage includes trigger boundaries; a browser component check covers selection and structured send payloads with a mocked lookup endpoint.

Real MongoDB and model-backed end-to-end validation are still required in a deployed test environment. Desktop Code sessions currently reject knowledge references explicitly because their local IPC contract does not transport these structured materials; ordinary server-backed chat is the supported path.
