#!/usr/bin/env python3
"""
Schema markup generator: Create JSON-LD from validated entities.
Generates schema.org compliant structured data.
"""

import json
import re
from datetime import date
from typing import Optional
from pathlib import Path


class SchemaGenerator:
    """Generate JSON-LD schema markup from validated entities."""
    
    TYPE_MAP = {
        'Person': 'Person',
        'Organization': 'Organization',
        'Place': 'Place',
        'Product': 'Product',
        'Event': 'Event',
    }
    
    def __init__(self, entity_library: list[dict], minimum_confidence: int = 60):
        self.library = {e.get('entity_id'): e for e in entity_library}
        self.minimum_confidence = minimum_confidence
    
    def generate(self, 
                 match_results: list[dict],
                 article_title: Optional[str] = None,
                 article_date: Optional[str] = None,
                 publisher_id: Optional[str] = None) -> dict:
        """Generate complete JSON-LD schema."""
        graph = []
        included_ids = set()
        
        article_schema = self._generate_article_schema(
            match_results, article_title, article_date, publisher_id
        )
        if article_schema:
            graph.append(article_schema)
        
        for result in match_results:
            if result.get('confidence_score', 0) < self.minimum_confidence:
                continue
            
            entity_id = result.get('matched_entity_id')
            
            if result.get('action') == 'use_existing' and entity_id:
                if entity_id not in included_ids:
                    entity_schema = self._generate_entity_schema(entity_id)
                    if entity_schema:
                        graph.append(entity_schema)
                        included_ids.add(entity_id)
            
            elif result.get('action') in ['auto_add_active', 'auto_add_pending']:
                suggested = result.get('suggested_entry', {})
                if suggested:
                    entity_schema = self._generate_schema_from_entry(suggested)
                    if entity_schema:
                        graph.append(entity_schema)
                        included_ids.add(suggested.get('entity_id'))
        
        additional_ids = self._find_linked_entities(included_ids)
        for entity_id in additional_ids:
            if entity_id not in included_ids:
                entity_schema = self._generate_entity_schema(entity_id)
                if entity_schema:
                    graph.append(entity_schema)
                    included_ids.add(entity_id)
        
        return {"@context": "https://schema.org", "@graph": graph}
    
    def _generate_article_schema(self, match_results: list[dict],
                                 title: Optional[str],
                                 pub_date: Optional[str],
                                 publisher_id: Optional[str]) -> Optional[dict]:
        schema = {"@type": "Article", "@id": "#article"}
        
        if title:
            schema["headline"] = title
        
        schema["datePublished"] = pub_date or date.today().isoformat()
        
        for result in match_results:
            entity_id = result.get('matched_entity_id')
            if entity_id and entity_id.startswith('person-'):
                schema["author"] = {"@id": f"#{entity_id}"}
                break
            suggested = result.get('suggested_entry', {})
            if suggested.get('entity_type') == 'Person':
                schema["author"] = {"@id": f"#{suggested.get('entity_id')}"}
                break
        
        if publisher_id:
            schema["publisher"] = {"@id": f"#{publisher_id}"}
        
        return schema
    
    def _generate_entity_schema(self, entity_id: str) -> Optional[dict]:
        entity = self.library.get(entity_id)
        return self._generate_schema_from_entry(entity) if entity else None
    
    def _generate_schema_from_entry(self, entity: dict) -> Optional[dict]:
        entity_type = entity.get('entity_type')
        if entity_type not in self.TYPE_MAP:
            return None
        
        schema = {
            "@type": self.TYPE_MAP[entity_type],
            "@id": f"#{entity.get('entity_id')}",
            "name": entity.get('canonical_name', ''),
        }
        
        if entity.get('description'):
            schema["description"] = entity['description']
        if entity.get('url'):
            schema["url"] = entity['url']
        if entity.get('image_url'):
            schema["image"] = entity['image_url']
        
        if entity_type == 'Person':
            self._add_person_fields(schema, entity)
        elif entity_type == 'Organization':
            self._add_organization_fields(schema, entity)
        elif entity_type == 'Place':
            self._add_place_fields(schema, entity)
        elif entity_type == 'Product':
            self._add_product_fields(schema, entity)
        elif entity_type == 'Event':
            self._add_event_fields(schema, entity)
        
        if entity.get('same_as'):
            same_as = [s.strip() for s in entity['same_as'].split(',') if s.strip()]
            if same_as:
                schema["sameAs"] = same_as
        
        return schema
    
    def _add_person_fields(self, schema: dict, entity: dict):
        if entity.get('job_title'):
            schema["jobTitle"] = entity['job_title']
        
        if entity.get('works_for'):
            works_for = entity['works_for']
            if works_for.startswith('org-') or works_for in self.library:
                schema["worksFor"] = {"@id": f"#{works_for}"}
            else:
                for eid, e in self.library.items():
                    if e.get('canonical_name', '').lower() == works_for.lower():
                        schema["worksFor"] = {"@id": f"#{eid}"}
                        break
                else:
                    schema["worksFor"] = {"@type": "Organization", "name": works_for}
    
    def _add_organization_fields(self, schema: dict, entity: dict):
        if entity.get('logo_url'):
            schema["logo"] = entity['logo_url']
        if entity.get('founding_date'):
            schema["foundingDate"] = entity['founding_date']
        if entity.get('location'):
            location = entity['location']
            if location.startswith('place-') or location in self.library:
                schema["location"] = {"@id": f"#{location}"}
            else:
                schema["location"] = {"@type": "Place", "name": location}
    
    def _add_place_fields(self, schema: dict, entity: dict):
        if entity.get('address'):
            addr = entity['address']
            if isinstance(addr, dict):
                schema["address"] = {"@type": "PostalAddress", **addr}
            else:
                schema["address"] = addr
        if entity.get('geo_coordinates'):
            geo = entity['geo_coordinates']
            if isinstance(geo, dict):
                schema["geo"] = {"@type": "GeoCoordinates", **geo}
    
    def _add_product_fields(self, schema: dict, entity: dict):
        if entity.get('brand'):
            brand = entity['brand']
            if brand.startswith('org-') or brand in self.library:
                schema["brand"] = {"@id": f"#{brand}"}
            else:
                schema["brand"] = {"@type": "Brand", "name": brand}
        if entity.get('category'):
            schema["category"] = entity['category']
    
    def _add_event_fields(self, schema: dict, entity: dict):
        if entity.get('start_date'):
            schema["startDate"] = entity['start_date']
        if entity.get('end_date'):
            schema["endDate"] = entity['end_date']
        if entity.get('location'):
            location = entity['location']
            if location.startswith('place-') or location in self.library:
                schema["location"] = {"@id": f"#{location}"}
            else:
                schema["location"] = {"@type": "Place", "name": location}
        if entity.get('organizer'):
            organizer = entity['organizer']
            if organizer.startswith('org-') or organizer in self.library:
                schema["organizer"] = {"@id": f"#{organizer}"}
            else:
                schema["organizer"] = {"@type": "Organization", "name": organizer}
    
    def _find_linked_entities(self, included_ids: set) -> set:
        """Find entities referenced by included entities but not yet included."""
        linked = set()
        
        for entity_id in included_ids:
            entity = self.library.get(entity_id)
            if not entity:
                continue
            
            for field in ['works_for', 'brand', 'location', 'organizer']:
                ref = entity.get(field, '')
                if ref and (ref.startswith(('org-', 'place-', 'person-')) or ref in self.library):
                    linked.add(ref)
        
        return linked - included_ids
    
    def to_json(self, schema: dict, indent: int = 2) -> str:
        return json.dumps(schema, indent=indent, ensure_ascii=False)
    
    def to_script_tag(self, schema: dict) -> str:
        json_str = self.to_json(schema)
        return f'<script type="application/ld+json">\n{json_str}\n</script>'


def generate_schema(article_text: str,
                   entity_library: list[dict],
                   match_results: list[dict],
                   article_title: Optional[str] = None,
                   article_date: Optional[str] = None,
                   publisher_id: Optional[str] = None,
                   minimum_confidence: int = 60) -> dict:
    """
    Main function to generate schema for an article.
    
    Args:
        article_text: Article markdown (used to extract title if not provided)
        entity_library: Entity library entries
        match_results: Results from entity matching
        article_title: Override title
        article_date: Override date
        publisher_id: Entity ID of publisher
        minimum_confidence: Minimum score to include entity
        
    Returns:
        JSON-LD schema dict
    """
    if not article_title:
        h1_match = re.search(r'^#\s+(.+)$', article_text, re.MULTILINE)
        if h1_match:
            article_title = h1_match.group(1).strip()
    
    generator = SchemaGenerator(entity_library, minimum_confidence)
    return generator.generate(match_results, article_title, article_date, publisher_id)


def main():
    """CLI interface for schema generation."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Generate JSON-LD schema')
    parser.add_argument('article', help='Markdown article file')
    parser.add_argument('library', help='JSON file with entity library')
    parser.add_argument('matches', help='JSON file with match results')
    parser.add_argument('-o', '--output', help='Output file for JSON-LD')
    parser.add_argument('-t', '--title', help='Override article title')
    parser.add_argument('-d', '--date', help='Override publication date')
    parser.add_argument('-p', '--publisher', help='Publisher entity ID')
    parser.add_argument('--min-confidence', type=int, default=60,
                        help='Minimum confidence score (default: 60)')
    parser.add_argument('--script-tag', action='store_true',
                        help='Output as HTML script tag')
    
    args = parser.parse_args()
    
    article_text = Path(args.article).read_text()
    library = json.loads(Path(args.library).read_text())
    matches = json.loads(Path(args.matches).read_text())
    
    schema = generate_schema(
        article_text=article_text,
        entity_library=library,
        match_results=matches,
        article_title=args.title,
        article_date=args.date,
        publisher_id=args.publisher,
        minimum_confidence=args.min_confidence,
    )
    
    generator = SchemaGenerator(library)
    if args.script_tag:
        output = generator.to_script_tag(schema)
    else:
        output = generator.to_json(schema)
    
    if args.output:
        Path(args.output).write_text(output)
    else:
        print(output)


if __name__ == '__main__':
    main()
