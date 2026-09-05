# Entity Types Reference

## Supported Entity Types

### Person

Individuals mentioned in content.

**Extraction patterns:**
- Named individuals with titles: "John Smith, CEO"
- Authors/bylines: "By Jane Doe"
- Quoted sources: "'...' said Michael Chen"
- Team members: "Our CTO, Sarah Williams"

**Required fields:**
- canonical_name
- description

**Optional fields:**
- job_title
- works_for (link to Organization entity_id)
- url (personal site, LinkedIn)
- image_url
- same_as (Wikipedia, social profiles)

**NLP labels:** PERSON, PER

---

### Organization

Companies, institutions, agencies, teams.

**Extraction patterns:**
- Company names: "Acme Corp announced..."
- Institutions: "Stanford University researchers..."
- Agencies: "The FDA approved..."
- With context: "tech giant Google"

**Required fields:**
- canonical_name
- description

**Optional fields:**
- url (official website)
- logo_url
- same_as (Wikipedia, stock ticker)
- founding_date
- location (link to Place entity_id)

**NLP labels:** ORG, ORGANIZATION

---

### Place

Locations, addresses, geographic entities.

**Extraction patterns:**
- Cities/countries: "based in San Francisco"
- Addresses: "located at 123 Main St"
- Regions: "across the European Union"
- Landmarks: "near the Golden Gate Bridge"

**Required fields:**
- canonical_name

**Optional fields:**
- description
- url
- address
- geo_coordinates

**NLP labels:** GPE, LOC, LOCATION, FAC

---

### Product

Products, services, software, offerings.

**Extraction patterns:**
- Named products: "using Salesforce CRM"
- Services: "their cloud hosting service"
- With versions: "Windows 11"
- Branded items: "the new iPhone 15"

**Required fields:**
- canonical_name
- description

**Optional fields:**
- url (product page)
- image_url
- brand (link to Organization entity_id)
- category

**NLP labels:** PRODUCT (custom model required)

---

### Event

Conferences, launches, occurrences.

**Extraction patterns:**
- Named events: "at CES 2026"
- Recurring: "during the annual summit"
- Historical: "following the 2008 financial crisis"

**Required fields:**
- canonical_name

**Optional fields:**
- description
- start_date
- end_date
- location (link to Place entity_id)
- url
- organizer (link to Organization entity_id)

**NLP labels:** EVENT

---

## Extraction Pipeline

```
Raw Text
    │
    ▼
┌─────────────────────────┐
│  spaCy NER              │  ← Base entity recognition
│  (en_core_web_trf)      │
└─────────────────────────┘
    │
    ▼
┌─────────────────────────┐
│  Context Enhancement    │  ← Extract titles, roles, relationships
└─────────────────────────┘
    │
    ▼
┌─────────────────────────┐
│  Entity Deduplication   │  ← Merge "John Smith" and "Mr. Smith"
└─────────────────────────┘
    │
    ▼
┌─────────────────────────┐
│  Type Classification    │  ← Assign entity_type
└─────────────────────────┘
    │
    ▼
Extracted Entities List
```

## Context Enhancement Patterns

### Person Title Extraction

```python
patterns = [
    r"(\w+(?:\s+\w+)?),\s+(CEO|CTO|CFO|COO|President|Director|Manager|Founder|Co-founder)",
    r"(CEO|CTO|CFO|COO|President|Director)\s+(\w+(?:\s+\w+)?)",
    r"(\w+(?:\s+\w+)?),\s+(?:the\s+)?(head|chief|lead|senior)\s+(?:of\s+)?(\w+)",
]
```

### Organization Context

```python
patterns = [
    r"(?:at|from|of|with)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*(?:\s+(?:Inc|Corp|LLC|Ltd|Co)\.?)?)",
    r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(?:announced|released|launched|said)",
]
```

## Alias Generation

When adding entities, generate common aliases:

| Canonical | Generated Aliases |
|-----------|-------------------|
| Jonathan Smith | Jon Smith, J. Smith, Jonathan S. |
| Acme Corporation | Acme Corp, Acme, ACME |
| San Francisco, CA | San Francisco, SF, Bay Area |

## Entity ID Format

```
{type}-{slugified-canonical-name}

Examples:
- person-jonathan-smith
- org-acme-corp
- place-san-francisco-ca
- product-salesforce-crm
- event-ces-2026
```
