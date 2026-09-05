# Schema Mappings Reference

## Entity Type to Schema.org Mapping

| Entity Type | Schema.org Type | Notes |
|-------------|-----------------|-------|
| Person | schema:Person | |
| Organization | schema:Organization | Use LocalBusiness for local businesses |
| Place | schema:Place | Use LocalBusiness if also an org |
| Product | schema:Product | Use SoftwareApplication for software |
| Event | schema:Event | |
| Article | schema:Article | Auto-generated for the content itself |

## Property Mappings

### Person → schema:Person

| Entity Field | Schema Property |
|--------------|-----------------|
| canonical_name | name |
| description | description |
| job_title | jobTitle |
| works_for | worksFor → @id reference |
| url | url |
| image_url | image |
| same_as | sameAs (array) |

**Example:**

```json
{
  "@type": "Person",
  "@id": "#person-jonathan-smith",
  "name": "Jonathan Smith",
  "description": "Founder and CEO of Acme Corp with 20 years in enterprise software.",
  "jobTitle": "Founder & CEO",
  "worksFor": {
    "@id": "#org-acme-corp"
  },
  "url": "https://linkedin.com/in/jonathansmith",
  "image": "https://acme-corp.com/images/jonathan.jpg",
  "sameAs": [
    "https://twitter.com/jonathansmith",
    "https://linkedin.com/in/jonathansmith"
  ]
}
```

---

### Organization → schema:Organization

| Entity Field | Schema Property |
|--------------|-----------------|
| canonical_name | name |
| description | description |
| url | url |
| logo_url | logo |
| same_as | sameAs (array) |
| founding_date | foundingDate |
| location | location → @id reference |

**Example:**

```json
{
  "@type": "Organization",
  "@id": "#org-acme-corp",
  "name": "Acme Corp",
  "description": "Enterprise software company specializing in CRM solutions.",
  "url": "https://acme-corp.com",
  "logo": "https://acme-corp.com/logo.png",
  "foundingDate": "2010",
  "sameAs": [
    "https://www.linkedin.com/company/acme-corp",
    "https://en.wikipedia.org/wiki/Acme_Corp"
  ]
}
```

---

### Place → schema:Place

| Entity Field | Schema Property |
|--------------|-----------------|
| canonical_name | name |
| description | description |
| url | url |
| address | address (PostalAddress or text) |
| geo_coordinates | geo (GeoCoordinates) |

**Example:**

```json
{
  "@type": "Place",
  "@id": "#place-san-francisco-ca",
  "name": "San Francisco, CA",
  "description": "Major city in Northern California.",
  "address": {
    "@type": "PostalAddress",
    "addressLocality": "San Francisco",
    "addressRegion": "CA",
    "addressCountry": "US"
  },
  "geo": {
    "@type": "GeoCoordinates",
    "latitude": 37.7749,
    "longitude": -122.4194
  }
}
```

---

### Product → schema:Product

| Entity Field | Schema Property |
|--------------|-----------------|
| canonical_name | name |
| description | description |
| url | url |
| image_url | image |
| brand | brand → @id reference |
| category | category |

**Example:**

```json
{
  "@type": "Product",
  "@id": "#product-acme-crm-pro",
  "name": "Acme CRM Pro",
  "description": "Enterprise customer relationship management software.",
  "url": "https://acme-corp.com/products/crm-pro",
  "image": "https://acme-corp.com/images/crm-pro.png",
  "brand": {
    "@id": "#org-acme-corp"
  },
  "category": "Business Software"
}
```

---

### Event → schema:Event

| Entity Field | Schema Property |
|--------------|-----------------|
| canonical_name | name |
| description | description |
| start_date | startDate |
| end_date | endDate |
| location | location → @id reference |
| url | url |
| organizer | organizer → @id reference |

**Example:**

```json
{
  "@type": "Event",
  "@id": "#event-acme-summit-2026",
  "name": "Acme Summit 2026",
  "description": "Annual customer conference.",
  "startDate": "2026-06-15",
  "endDate": "2026-06-17",
  "location": {
    "@id": "#place-san-francisco-ca"
  },
  "url": "https://acme-corp.com/summit",
  "organizer": {
    "@id": "#org-acme-corp"
  }
}
```

---

### Article → schema:Article (Auto-Generated)

Always generated for the article itself:

| Source | Schema Property |
|--------|-----------------|
| H1 or title | headline |
| First Person entity | author → @id reference |
| Processing date | datePublished |
| Article content | articleBody (optional, usually omitted) |

**Example:**

```json
{
  "@type": "Article",
  "@id": "#article",
  "headline": "How to Choose the Best CRM for Your Business",
  "author": {
    "@id": "#person-jonathan-smith"
  },
  "datePublished": "2026-01-17",
  "publisher": {
    "@id": "#org-acme-corp"
  }
}
```

---

## Full Graph Structure

All entities are combined into a `@graph` array:

```json
{
  "@context": "https://schema.org",
  "@graph": [
    { "@type": "Article", ... },
    { "@type": "Person", ... },
    { "@type": "Organization", ... },
    { "@type": "Place", ... }
  ]
}
```

## Linking Entities

Use `@id` references to link entities within the graph:

```json
{
  "@type": "Person",
  "@id": "#person-jonathan-smith",
  "name": "Jonathan Smith",
  "worksFor": {
    "@id": "#org-acme-corp"
  }
}
```

The `#` prefix indicates a local reference within the same document.

## Validation Rules

Before generating schema:

1. **Required fields present** — Entity must have all required fields for its type
2. **Confidence threshold met** — Entity must meet minimum_for_schema threshold
3. **Valid references** — All @id references must point to entities in the graph
4. **No orphan references** — Don't reference entities that failed validation
