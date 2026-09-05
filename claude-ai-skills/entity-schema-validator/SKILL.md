---
name: entity-schema-validator
description: |
  Entity extraction, validation, and schema markup generator for articles. Use when processing article content to: (1) Extract entities (people, organizations, places, products) using NLP, (2) Validate entities against a client's Google Drive entity library, (3) Cross-reference with existing site content for consistency, (4) Auto-correct entity inconsistencies in article text, (5) Generate JSON-LD schema markup, (6) Audit and auto-patch entity library gaps. Triggers on article validation, schema generation, entity checking, or content consistency tasks.
---

# Entity Schema Validator

Validates entities in articles against a client's entity library and generates schema.org markup.

## Workflow Overview

```
Article (Markdown) Input
         │
         ▼
┌─────────────────────────┐
│  1. Extract Entities    │  ← NLP-based extraction
└─────────────────────────┘
         │
         ▼
┌─────────────────────────┐
│  2. Match & Validate    │  ← Compare against library + site content
└─────────────────────────┘
         │
         ▼
┌─────────────────────────┐
│  3. Auto-Correct Text   │  ← Fix inconsistencies in article
└─────────────────────────┘
         │
         ▼
┌─────────────────────────┐
│  4. Patch Library       │  ← Add missing entities (by confidence)
└─────────────────────────┘
         │
         ▼
┌─────────────────────────┐
│  5. Generate Schema     │  ← JSON-LD for validated entities
└─────────────────────────┘
         │
         ▼
┌─────────────────────────┐
│  6. Generate Report     │  ← Update spreadsheet tabs
└─────────────────────────┘
         │
         ▼
Corrected Markdown + Schema Output
```

## Quick Start

```python
from entity_validator import EntityValidator

validator = EntityValidator(
    client_config="config/clients/acme-corp.json"
)

result = validator.process_article("path/to/article.md")

# Outputs:
# - result.corrected_markdown  (article with fixed entities)
# - result.schema_json         (JSON-LD markup)
# - result.report              (validation summary)
```

## Client Configuration

Each client requires a config file at `config/clients/{client_id}.json`:

```json
{
  "client_id": "acme-corp",
  "entity_library_url": "https://docs.google.com/spreadsheets/d/xxx",
  "site_index_source": "https://acme-corp.com/sitemap.xml",
  
  "confidence_thresholds": {
    "auto_add_active": 85,
    "auto_add_pending": 60,
    "minimum_for_schema": 60
  },
  
  "factor_weights": {
    "exact_site_match": 30,
    "partial_site_match": 15,
    "consistent_context": 20,
    "linked_entity": 15,
    "structured_data_found": 10,
    "web_corroboration": 10
  },
  
  "staleness_config": {
    "days_until_stale": 90,
    "auto_reverify_on_use": true,
    "flag_conflicts_for_review": true
  },
  
  "source_priority": ["library", "site_content", "site_schema", "web_search"]
}
```

## Entity Library Structure

The Google Sheet must have these tabs:

### Tab 1: Active Entities (required columns)

| Column | Required | Description |
|--------|----------|-------------|
| entity_id | ✓ | Unique ID (e.g., `person-jonathan-smith`) |
| entity_type | ✓ | Person, Organization, Product, Place, Event |
| canonical_name | ✓ | Correct name to use in content |
| aliases | | Comma-separated alternatives |
| description | ✓ | Short bio/description for schema |
| url | | Official website or profile |
| image_url | | Photo/logo URL |
| job_title | | For Person type |
| works_for | | Links to Organization entity_id |
| same_as | | External identifiers (LinkedIn, Wikipedia) |
| last_verified | ✓ | Date last confirmed accurate |
| status | ✓ | active, pending_review, deprecated, stale |

### Tab 2: Pending Review

Auto-populated with entities needing human verification.

### Tab 3: Audit Log

History of all entity additions, modifications, and validations.

## Confidence Scoring

Entities are scored based on source corroboration:

| Factor | Weight | Trigger |
|--------|--------|---------|
| Exact site match | +30% | Entity appears identically in indexed pages |
| Partial site match | +15% | Similar name/context found |
| Consistent context | +20% | Same details across multiple sources |
| Linked entity | +15% | References known entity in library |
| Structured data found | +10% | Existing schema on site |
| Web corroboration | +10% | Web search agrees (lowest priority) |

### Thresholds

- **85-100%**: Auto-add as `active`
- **60-84%**: Auto-add as `pending_review`
- **Below 60%**: Log only, no schema generated

## Source Priority

Information is sourced in this order (higher = more trusted):

1. **Entity Library** — Single source of truth
2. **Indexed Site Content** — /about, /team, author bios, existing articles
3. **Existing Site Schema** — JSON-LD already on site
4. **Web Search** — Corroboration only, never overrides higher sources

## Scripts

### Main Processing

- `scripts/process_article.py` — Full pipeline for single article
- `scripts/batch_process.py` — Process multiple articles

### Entity Operations

- `scripts/extract_entities.py` — NLP extraction from text
- `scripts/match_entities.py` — Match extracted to library with confidence
- `scripts/correct_content.py` — Apply corrections to article text

### Library Operations

- `scripts/index_site.py` — Crawl sitemap and index content
- `scripts/audit_library.py` — Generate library health report
- `scripts/sync_library.py` — Read/write Google Sheets

### Schema Generation

- `scripts/generate_schema.py` — Create JSON-LD from validated entities

## Output Format

### Corrected Article (Markdown with frontmatter)

```markdown
---
schema:
  - type: Article
    headline: "How to Choose the Best CRM"
    author: "@entity/person-jonathan-smith"
    datePublished: "2026-01-17"
  - type: Person
    "@ref": "person-jonathan-smith"
  - type: Organization
    "@ref": "org-acme-corp"
validation:
  entities_found: 7
  matched: 5
  auto_added: 1
  pending_review: 1
  confidence_avg: 82
---

# How to Choose the Best CRM

Jonathan Smith, Founder & CEO of Acme Corp, explains...
```

### Schema Output (JSON-LD)

```json
{
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "Article",
      "headline": "How to Choose the Best CRM",
      "author": { "@id": "#person-jonathan-smith" },
      "datePublished": "2026-01-17"
    },
    {
      "@type": "Person",
      "@id": "#person-jonathan-smith",
      "name": "Jonathan Smith",
      "jobTitle": "Founder & CEO",
      "worksFor": { "@id": "#org-acme-corp" }
    },
    {
      "@type": "Organization",
      "@id": "#org-acme-corp",
      "name": "Acme Corp",
      "url": "https://acme-corp.com"
    }
  ]
}
```

## References

- `references/entity_types.md` — Supported entity types and extraction patterns
- `references/schema_mappings.md` — Entity type to schema.org type mappings
- `references/confidence_scoring.md` — Detailed scoring algorithm

## Assets

- `assets/schema_templates/` — JSON-LD templates for each entity type
