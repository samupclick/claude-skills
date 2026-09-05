# Confidence Scoring Reference

## Overview

Every extracted entity receives a confidence score (0-100%) determining how it's handled:

| Score | Classification | Action |
|-------|----------------|--------|
| 85-100% | High confidence | Auto-add to library as `active` |
| 60-84% | Medium confidence | Auto-add as `pending_review` |
| 0-59% | Low confidence | Log only, no schema generated |

## Scoring Factors

### Factor 1: Exact Site Match (+30%)

**Trigger:** Entity name appears identically in indexed site content.

**Implementation:**
```python
def check_exact_site_match(entity_name, site_index):
    for page in site_index:
        if entity_name.lower() in page.text.lower():
            # Verify it's not a substring of something else
            if is_standalone_mention(entity_name, page.text):
                return 0.30
    return 0.0
```

**Examples:**
- ✅ "Jonathan Smith" found on /about page → +30%
- ✅ "Acme Corp" found in footer → +30%
- ❌ "Jon" found (too short, likely substring) → +0%

---

### Factor 2: Partial Site Match (+15%)

**Trigger:** Similar name or alias found on site.

**Implementation:**
```python
def check_partial_site_match(entity_name, site_index):
    variants = generate_variants(entity_name)
    # variants: ["J. Smith", "Jonathan S.", "Jon Smith", etc.]
    
    for page in site_index:
        for variant in variants:
            if variant.lower() in page.text.lower():
                return 0.15
    return 0.0
```

**Examples:**
- ✅ Extracted "Jon Smith", found "Jonathan Smith" on site → +15%
- ✅ Extracted "Acme", found "Acme Corporation" → +15%
- ❌ No similar names found → +0%

---

### Factor 3: Consistent Context (+20%)

**Trigger:** Same entity details appear across multiple sources.

**Implementation:**
```python
def check_consistent_context(entity, sources):
    """
    Check if entity attributes (title, org, description) are 
    consistent across multiple mentions.
    """
    mentions = find_all_mentions(entity.name, sources)
    
    if len(mentions) < 2:
        return 0.0
    
    # Extract context from each mention
    contexts = [extract_context(m) for m in mentions]
    
    # Check consistency
    if contexts_agree(contexts):
        return 0.20
    elif contexts_mostly_agree(contexts, threshold=0.7):
        return 0.10
    return 0.0
```

**Examples:**
- ✅ "Sarah Chen, CTO" in 3 articles, all say CTO → +20%
- ⚠️ 2 say "CTO", 1 says "Chief Technology Officer" → +10% (mostly agree)
- ❌ 1 says "CTO", 1 says "VP Engineering" → +0% (conflict)

---

### Factor 4: Linked Entity (+15%)

**Trigger:** Entity references another entity already in the library.

**Implementation:**
```python
def check_linked_entity(entity, library):
    """
    Check if entity mentions an organization/person already in library.
    """
    if entity.type == "Person" and entity.works_for:
        if library.find_by_name(entity.works_for):
            return 0.15
    
    if entity.type == "Product" and entity.brand:
        if library.find_by_name(entity.brand):
            return 0.15
    
    return 0.0
```

**Examples:**
- ✅ "Sarah Chen, CTO at Acme Corp" where Acme Corp is in library → +15%
- ✅ "Acme CRM Pro" product where Acme Corp is in library → +15%
- ❌ References unknown organization → +0%

---

### Factor 5: Structured Data Found (+10%)

**Trigger:** Entity appears in existing JSON-LD on the site.

**Implementation:**
```python
def check_structured_data(entity_name, site_index):
    for page in site_index:
        for schema in page.json_ld_blocks:
            if entity_matches_schema(entity_name, schema):
                return 0.10
    return 0.0
```

**Examples:**
- ✅ Found `{"@type": "Person", "name": "Jonathan Smith"}` on /about → +10%
- ✅ Found in Organization schema → +10%
- ❌ No structured data on site → +0%

---

### Factor 6: Web Corroboration (+10%)

**Trigger:** Web search results support entity details.

**Note:** Lowest weight — only used to supplement, never to override.

**Implementation:**
```python
def check_web_corroboration(entity):
    """
    Search web for entity and verify details match.
    """
    query = f"{entity.name} {entity.works_for or ''}"
    results = web_search(query, limit=5)
    
    if not results:
        return 0.0
    
    # Check if results support our entity data
    supporting_results = 0
    for result in results:
        if entity_details_match(entity, result):
            supporting_results += 1
    
    if supporting_results >= 2:
        return 0.10
    elif supporting_results == 1:
        return 0.05
    return 0.0
```

**Examples:**
- ✅ LinkedIn + company site both confirm "Sarah Chen, CTO" → +10%
- ⚠️ Only one source confirms → +5%
- ❌ Conflicting info or no results → +0%

---

## Scoring Algorithm

```python
def calculate_confidence(entity, library, site_index, web_enabled=True):
    score = 0.0
    factors = {}
    
    # Check each factor
    factors['exact_site_match'] = check_exact_site_match(entity.name, site_index)
    factors['partial_site_match'] = check_partial_site_match(entity.name, site_index)
    factors['consistent_context'] = check_consistent_context(entity, site_index)
    factors['linked_entity'] = check_linked_entity(entity, library)
    factors['structured_data'] = check_structured_data(entity.name, site_index)
    
    if web_enabled:
        factors['web_corroboration'] = check_web_corroboration(entity)
    
    # Sum factors (capped at 1.0)
    score = min(sum(factors.values()), 1.0)
    
    return {
        'score': round(score * 100),
        'factors': factors,
        'classification': classify_score(score)
    }

def classify_score(score):
    if score >= 0.85:
        return 'high'
    elif score >= 0.60:
        return 'medium'
    return 'low'
```

---

## Example Calculations

### Example 1: High Confidence (92%)

```
Entity: Jonathan Smith, Founder & CEO

Factors:
  ✅ exact_site_match:     +30%  (found on /about page)
  ✅ partial_site_match:   +0%   (exact match already found)
  ✅ consistent_context:   +20%  (same title in 4 articles)
  ✅ linked_entity:        +15%  (works_for: Acme Corp exists)
  ✅ structured_data:      +10%  (in Person schema on /about)
  ✅ web_corroboration:    +10%  (LinkedIn confirms)
  ─────────────────────────────
  Total:                   92%   → HIGH CONFIDENCE
  
Action: Auto-add to library as 'active'
```

### Example 2: Medium Confidence (71%)

```
Entity: Michael Torres, Head of Product

Factors:
  ✅ exact_site_match:     +30%  (found in blog post)
  ❌ partial_site_match:   +0%   (exact match found)
  ⚠️ consistent_context:   +10%  (2 mentions, minor title variation)
  ✅ linked_entity:        +15%  (works_for: Acme Corp exists)
  ❌ structured_data:      +0%   (no schema for this person)
  ⚠️ web_corroboration:    +5%   (only 1 source confirms)
  ─────────────────────────────
  Total:                   71%   → MEDIUM CONFIDENCE

Action: Auto-add to library as 'pending_review'
```

### Example 3: Low Confidence (23%)

```
Entity: David (consultant)

Factors:
  ❌ exact_site_match:     +0%   (no "David" standalone)
  ❌ partial_site_match:   +0%   (name too common/vague)
  ❌ consistent_context:   +0%   (only 1 mention)
  ❌ linked_entity:        +0%   (no org linked)
  ❌ structured_data:      +0%   (not in any schema)
  ⚠️ web_corroboration:    +0%   (too ambiguous to search)
  ─────────────────────────────
  Total:                   23%   → LOW CONFIDENCE

Action: Log only, no schema generated, flag for manual review
```

---

## Configuring Weights

Weights are configurable per client in `config/clients/{client_id}.json`:

```json
{
  "factor_weights": {
    "exact_site_match": 30,
    "partial_site_match": 15,
    "consistent_context": 20,
    "linked_entity": 15,
    "structured_data_found": 10,
    "web_corroboration": 10
  }
}
```

Adjust weights based on:
- **New sites** (little content): Lower site match weights, higher web corroboration
- **Established sites** (rich content): Higher site match weights
- **Sensitive industries**: Higher thresholds overall
