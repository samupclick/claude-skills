---
name: aeo-entity-master
description: |
  Advanced AEO (Answer Engine Optimization) schema generator for maximum AI citation potential. 
  Extends basic entity validation with automatic detection of FAQ, HowTo, comparison tables, 
  definitions, and statistics. Generates comprehensive JSON-LD markup optimized for LLM citation, 
  voice search, and featured snippets. Use when: (1) Processing articles for AEO-optimized schema, 
  (2) Generating FAQPage, HowTo, ItemList, DefinedTerm schema from content patterns, 
  (3) Creating rich author/expertise schema for E-E-A-T signals, (4) Extracting and citing 
  statistics with proper Claim schema, (5) Adding SpeakableSpecification for voice search.
---

# AEO Entity Master

Enterprise-grade schema generation optimized for Answer Engine Optimization. Automatically detects content patterns and generates comprehensive JSON-LD markup that maximizes AI citation potential.

## What Makes This Different from Basic Entity Validation

| Capability | entity-schema-validator | aeo-entity-master |
|------------|------------------------|-------------------|
| Entity extraction (Person, Org, etc.) | ✓ | ✓ |
| Basic Article schema | ✓ | ✓ |
| FAQPage auto-detection | ✗ | ✓ |
| HowTo auto-detection | ✗ | ✓ |
| Comparison table → ItemList | ✗ | ✓ |
| DefinedTerm extraction | ✗ | ✓ |
| Claim schema for statistics | ✗ | ✓ |
| SpeakableSpecification | ✗ | ✓ |
| Rich author E-E-A-T fields | Limited | Full |
| Content structure analysis | ✗ | ✓ |

## Workflow Overview

```
Article (Markdown) Input
         │
         ▼
┌─────────────────────────────┐
│  1. Content Structure Scan  │  ← Detect FAQ, HowTo, Tables, Definitions
└─────────────────────────────┘
         │
         ▼
┌─────────────────────────────┐
│  2. Entity Extraction       │  ← NLP-based (Person, Org, Product, etc.)
└─────────────────────────────┘
         │
         ▼
┌─────────────────────────────┐
│  3. Statistics Extraction   │  ← Find percentages, costs, citations
└─────────────────────────────┘
         │
         ▼
┌─────────────────────────────┐
│  4. Library Validation      │  ← Match against entity library
└─────────────────────────────┘
         │
         ▼
┌─────────────────────────────┐
│  5. Schema Generation       │  ← Full @graph with all detected types
└─────────────────────────────┘
         │
         ▼
┌─────────────────────────────┐
│  6. Speakable Selection     │  ← Mark AEO snippets for voice search
└─────────────────────────────┘
         │
         ▼
Complete JSON-LD Output
```

## Quick Start

```python
from aeo_entity_master import AEOSchemaGenerator

generator = AEOSchemaGenerator(
    client_config="config/clients/hst-solutions.json"
)

result = generator.process_article("path/to/article.md")

# Outputs:
# - result.schema_json         (Complete JSON-LD with all detected types)
# - result.detected_patterns   (FAQ, HowTo, Table, Definition locations)
# - result.aeo_score           (0-100 rating of schema completeness)
# - result.recommendations     (Missing schema opportunities)
```

## Supported Schema Types

### Core Entity Types (inherited)
- `Person` — Authors, experts, quoted sources
- `Organization` — Companies, institutions, agencies
- `Place` — Locations, addresses
- `Product` — Products, services, software
- `Event` — Conferences, launches

### AEO Content Types (new)
- `FAQPage` — Question/answer sections
- `HowTo` — Step-by-step guides, migration paths
- `ItemList` — Comparison tables, rankings
- `DefinedTerm` — Technical terms, jargon definitions
- `Claim` — Statistics with cited sources
- `SpeakableSpecification` — Voice search optimization

### Enhanced Entity Fields (new)
- `knowsAbout` — Expertise areas for Person
- `hasCredential` — Certifications for Person
- `alumniOf` — Education for Person
- `citation` — Source attribution for Claim

## Content Pattern Detection

### FAQ Detection

Triggers `FAQPage` schema when:

```markdown
## FAQ                           ← Section header trigger
## Frequently Asked Questions    ← Section header trigger

**Q: What is staging-only?**     ← Q&A pattern
A: Staging-only workflows...

> **Question:** How long...      ← Blockquote Q&A
> **Answer:** Implementation...
```

Minimum: 2 Q&A pairs required.

### HowTo Detection

Triggers `HowTo` schema when:

```markdown
## How to Migrate Access Models  ← "How to" in header

## Transitioning Between Models  ← Step sequence detected below

**From full production access to staging-only:**
1. Begin by implementing...      ← Numbered steps
2. Configure development...
3. Gradually remove...

Timeline: 3-4 weeks              ← Duration extraction
```

### Table/ItemList Detection

Triggers `ItemList` schema when:

```markdown
| Factor | Option A | Option B | Option C |   ← 3+ columns
|--------|----------|----------|----------|
| Cost   | High     | Medium   | Low      |   ← Comparison data
| Speed  | Fast     | Medium   | Slow     |
```

### Definition Detection

Triggers `DefinedTerm` schema when:

```markdown
**Staging-only workflows** restrict external developers to...

**Hybrid tiered access** grants external developers limited...

*Separation of duties* means no single person has complete control...
```

Pattern: Bold/italic term followed by definition verb (restrict, grant, means, refers to, is defined as).

### Statistics/Claim Detection

Triggers `Claim` schema when:

```markdown
According to SecurityScorecard's 2025 Report, 35.5% of breaches...

Research shows that third-party breaches cost €4.5 million on average...
```

Pattern: Percentage or currency + source attribution.

## Client Configuration

Each client requires a config file at `config/clients/{client_id}.json`:

```json
{
  "client_id": "hst-solutions",
  "client_name": "HST Solutions",
  
  "entity_library_url": "https://docs.google.com/spreadsheets/d/xxx",
  "site_index_source": "https://www.hst.ie/sitemap.xml",
  "publisher_entity_id": "org-hst-solutions",
  
  "confidence_thresholds": {
    "auto_add_active": 85,
    "auto_add_pending": 60,
    "minimum_for_schema": 60
  },
  
  "aeo_features": {
    "auto_detect_faq": true,
    "auto_detect_howto": true,
    "auto_detect_definitions": true,
    "auto_detect_statistics": true,
    "table_to_itemlist": true,
    "generate_speakable": true,
    "speakable_selectors": [".aeo-snippet", ".key-takeaways"]
  },
  
  "author_enrichment": {
    "require_expertise": true,
    "require_credentials": false,
    "default_expertise_source": "library"
  },
  
  "source_priority": ["library", "site_content", "site_schema", "web_search"]
}
```

## Entity Library Structure

Extended Google Sheet structure for AEO:

### Tab 1: Active Entities

| Column | Required | Description |
|--------|----------|-------------|
| entity_id | ✓ | Unique ID (e.g., `person-kris-estigoy`) |
| entity_type | ✓ | Person, Organization, Product, Place, Event |
| canonical_name | ✓ | Correct name to use |
| aliases | | Comma-separated alternatives |
| description | ✓ | Short bio/description |
| url | | Official website or profile |
| image_url | | Photo/logo URL |
| same_as | | External identifiers (LinkedIn, Wikipedia) |
| last_verified | ✓ | Date last confirmed accurate |
| status | ✓ | active, pending_review, deprecated |

### Tab 2: Person Extended (new)

| Column | Description |
|--------|-------------|
| entity_id | Links to Active Entities |
| job_title | Current role |
| works_for | Organization entity_id |
| knows_about | Comma-separated expertise areas |
| has_credential | Certifications (e.g., "AWS Solutions Architect") |
| alumni_of | Education institutions |
| years_experience | Numeric |
| author_bio_short | 1-2 sentence bio for schema |

### Tab 3: Defined Terms (new)

| Column | Description |
|--------|-------------|
| term_id | Unique ID (e.g., `term-staging-only-workflow`) |
| term | The term as it appears in content |
| definition | Clear definition (1-2 sentences) |
| aliases | Alternative phrasings |
| url | Link to glossary or detailed explanation |
| in_defined_term_set | Optional DefinedTermSet ID |

### Tab 4: Claim Sources (new)

| Column | Description |
|--------|-------------|
| claim_id | Unique ID |
| claim_text | The statistic or claim |
| source_name | Publication/report name |
| source_org | Organization that published |
| source_url | Link to source |
| source_date | Publication date |
| last_verified | When we last checked accuracy |

## Output Format

### Complete Schema Example

For an article like the HST staging-only comparison, generates:

```json
{
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "Article",
      "@id": "https://www.hst.ie/blog/staging-only-vs-production-access/#article",
      "headline": "Staging-Only vs Production Access for External Teams",
      "description": "Compare full production access, staging-only workflows...",
      "author": {"@id": "#person-kris-estigoy"},
      "publisher": {"@id": "#org-hst-solutions"},
      "datePublished": "2026-01-19",
      "dateModified": "2026-01-19",
      "speakable": {
        "@type": "SpeakableSpecification",
        "cssSelector": [".aeo-snippet", ".key-takeaways"]
      }
    },
    {
      "@type": "Person",
      "@id": "#person-kris-estigoy",
      "name": "Kris Estigoy",
      "jobTitle": "Content Writer",
      "worksFor": {"@id": "#org-hst-solutions"},
      "knowsAbout": ["software development", "outsourcing", "compliance", "ISO 27001"]
    },
    {
      "@type": "Person",
      "@id": "#person-dave-quinn",
      "name": "Dave Quinn",
      "jobTitle": "Head of Software Engineering",
      "worksFor": {"@id": "#org-hst-solutions"},
      "knowsAbout": ["software architecture", "security", "DevOps", "cloud infrastructure"]
    },
    {
      "@type": "Organization",
      "@id": "#org-hst-solutions",
      "name": "HST Solutions",
      "url": "https://www.hst.ie",
      "logo": "https://www.hst.ie/wp-content/uploads/2024/12/logo.svg",
      "sameAs": ["https://www.linkedin.com/company/hst-solutions"]
    },
    {
      "@type": "FAQPage",
      "@id": "#faq",
      "mainEntity": [
        {
          "@type": "Question",
          "name": "Which access model satisfies ISO 27001 separation of duties?",
          "acceptedAnswer": {
            "@type": "Answer",
            "text": "Staging-only workflows satisfy ISO 27001 Annex A 5.3..."
          }
        }
      ]
    },
    {
      "@type": "HowTo",
      "@id": "#howto-migration",
      "name": "How to Transition Between Access Models",
      "step": [
        {
          "@type": "HowToStep",
          "name": "From full production to staging-only",
          "text": "Begin by implementing deployment pipeline gates...",
          "estimatedTime": "P3W"
        }
      ]
    },
    {
      "@type": "ItemList",
      "@id": "#comparison-table",
      "name": "Access Model Comparison",
      "itemListElement": [
        {
          "@type": "ListItem",
          "position": 1,
          "name": "Full Production Access",
          "description": "Fails separation of duties..."
        }
      ]
    },
    {
      "@type": "DefinedTerm",
      "@id": "#term-staging-only",
      "name": "Staging-only workflows",
      "description": "Access model that restricts external developers to development and staging environments only"
    },
    {
      "@type": "Claim",
      "@id": "#claim-breach-percentage",
      "claimReviewed": "35.5% of all data breaches in 2024 originated from third-party compromises",
      "appearance": {
        "@type": "CreativeWork",
        "name": "2025 Global Third-Party Breach Report",
        "author": {"@type": "Organization", "name": "SecurityScorecard"},
        "datePublished": "2025"
      }
    }
  ]
}
```

## AEO Score Calculation

The generator produces an AEO score (0-100) based on schema completeness:

| Component | Max Points | Criteria |
|-----------|------------|----------|
| Article base | 20 | headline, description, author, publisher, dates |
| Author richness | 15 | jobTitle, worksFor, knowsAbout, sameAs |
| FAQPage | 15 | Detected and generated (if FAQ content exists) |
| HowTo | 10 | Detected and generated (if step content exists) |
| ItemList | 10 | Tables converted to structured data |
| DefinedTerm | 10 | Technical terms with definitions |
| Claim citations | 10 | Statistics with proper attribution |
| Speakable | 10 | Voice search optimization present |

**Score interpretation:**
- 90-100: Exceptional AEO readiness
- 75-89: Good, minor improvements possible
- 60-74: Adequate, missing key opportunities
- Below 60: Significant gaps, review recommended

## Scripts

### Main Processing
- `scripts/process_article.py` — Full AEO pipeline for single article
- `scripts/batch_process.py` — Process multiple articles
- `scripts/audit_schema.py` — Score existing schema against AEO criteria

### Content Detection
- `scripts/detect_faq.py` — Extract FAQ patterns from markdown
- `scripts/detect_howto.py` — Extract step sequences
- `scripts/detect_tables.py` — Parse and structure comparison tables
- `scripts/detect_definitions.py` — Find term definitions
- `scripts/detect_statistics.py` — Extract claims with sources

### Schema Generation
- `scripts/generate_schema.py` — Main schema generator (extended)
- `scripts/generate_speakable.py` — Add SpeakableSpecification

### Validation
- `scripts/validate_schema.py` — Validate against schema.org
- `scripts/test_rich_results.py` — Test Google Rich Results eligibility

## References

- `references/aeo_content_patterns.md` — Detection patterns for all content types
- `references/schema_mappings.md` — Entity to schema.org mappings (extended)
- `references/eeat_signals.md` — E-E-A-T optimization guidance
- `references/speakable_best_practices.md` — Voice search optimization

## Assets

- `assets/schema_templates/` — JSON-LD templates for all schema types
