"""The material browsing tool contract, separate from the global capability catalog."""


def browse_definition(definition, object_schema):
    return definition(
        capability_ref="knowledge.browse@v1", tool_name="knowledge_browse", domain="knowledge",
        display_name="Browse knowledge materials",
        description=("List authorized documents in a selected MOVO directory, including descendants, or find documents by name. "
                     "Pass scope and directory_id from the user's materials. Continue using next_cursor even if a filtered page is empty. "
                     "Returned personal source_id values are resource IDs, not document IDs."),
        input_schema=object_schema({
            "scope": {"type": "string", "enum": ["personal", "organization"]},
            "directory_id": {"type": "string", "maxLength": 128},
            "query": {"type": "string", "maxLength": 120},
            "cursor": {"type": "integer", "minimum": 0, "maximum": 1000000},
        }, ("scope",)),
    )
