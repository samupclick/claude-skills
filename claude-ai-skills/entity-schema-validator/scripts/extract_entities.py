#!/usr/bin/env python3
"""
Entity extraction from article text using spaCy NLP.
Extracts people, organizations, places, products, and events.
"""

import re
import json
from dataclasses import dataclass, field, asdict
from typing import Optional
from pathlib import Path

try:
    import spacy
    from spacy.tokens import Span
except ImportError:
    spacy = None


@dataclass
class ExtractedEntity:
    """Represents an entity extracted from text."""
    name: str
    entity_type: str
    context: str = ""
    job_title: Optional[str] = None
    works_for: Optional[str] = None
    mentions: list = field(default_factory=list)
    confidence_factors: dict = field(default_factory=dict)
    
    def to_dict(self):
        return asdict(self)
    
    def generate_id(self) -> str:
        """Generate entity_id from type and name."""
        slug = re.sub(r'[^a-z0-9]+', '-', self.name.lower()).strip('-')
        type_prefix = self.entity_type.lower()
        return f"{type_prefix}-{slug}"


class EntityExtractor:
    """Extract entities from text using spaCy NLP."""
    
    # Map spaCy labels to our entity types
    LABEL_MAP = {
        'PERSON': 'Person',
        'PER': 'Person',
        'ORG': 'Organization',
        'ORGANIZATION': 'Organization',
        'GPE': 'Place',
        'LOC': 'Place',
        'LOCATION': 'Place',
        'FAC': 'Place',
        'EVENT': 'Event',
        'PRODUCT': 'Product',
        'WORK_OF_ART': 'Product',
    }
    
    # Patterns for extracting person titles
    TITLE_PATTERNS = [
        r"(\w+(?:\s+\w+)?),\s+(CEO|CTO|CFO|COO|CMO|President|Director|Manager|Founder|Co-founder|Chairman|Vice President|VP|Head of \w+)",
        r"(CEO|CTO|CFO|COO|CMO|President|Director|Founder|Chairman)\s+(\w+(?:\s+\w+)?)",
        r"(\w+(?:\s+\w+)?),\s+(?:the\s+)?(head|chief|lead|senior|principal)\s+(?:of\s+)?(\w+)",
    ]
    
    # Patterns for extracting organization context
    ORG_CONTEXT_PATTERNS = [
        r"(?:at|from|of|with)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*(?:\s+(?:Inc|Corp|LLC|Ltd|Co|Company|Corporation)\.?)?)",
        r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(?:announced|released|launched|reported|said|stated)",
    ]
    
    def __init__(self, model_name: str = "en_core_web_sm"):
        """
        Initialize extractor with spaCy model.
        
        Args:
            model_name: spaCy model to use. Options:
                - en_core_web_sm (fast, less accurate)
                - en_core_web_md (balanced)
                - en_core_web_lg (slower, more accurate)
                - en_core_web_trf (transformer, most accurate)
        """
        if spacy is None:
            raise ImportError("spaCy is required. Install with: pip install spacy")
        
        try:
            self.nlp = spacy.load(model_name)
        except OSError:
            raise OSError(f"Model {model_name} not found. Install with: python -m spacy download {model_name}")
    
    def extract(self, text: str) -> list[ExtractedEntity]:
        """
        Extract entities from text.
        
        Args:
            text: Article text (plain text or markdown)
            
        Returns:
            List of ExtractedEntity objects
        """
        # Clean markdown if present
        clean_text = self._clean_markdown(text)
        
        # Process with spaCy
        doc = self.nlp(clean_text)
        
        # Extract base entities
        raw_entities = self._extract_base_entities(doc)
        
        # Enhance with context
        enhanced = self._enhance_with_context(raw_entities, clean_text)
        
        # Deduplicate
        deduplicated = self._deduplicate(enhanced)
        
        return deduplicated
    
    def _clean_markdown(self, text: str) -> str:
        """Remove markdown formatting while preserving text."""
        # Remove frontmatter
        text = re.sub(r'^---\n.*?\n---\n', '', text, flags=re.DOTALL)
        
        # Remove code blocks
        text = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
        text = re.sub(r'`[^`]+`', '', text)
        
        # Remove links but keep text
        text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
        
        # Remove images
        text = re.sub(r'!\[.*?\]\(.*?\)', '', text)
        
        # Remove headers markup but keep text
        text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
        
        # Remove bold/italic
        text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
        text = re.sub(r'\*([^*]+)\*', r'\1', text)
        text = re.sub(r'__([^_]+)__', r'\1', text)
        text = re.sub(r'_([^_]+)_', r'\1', text)
        
        return text.strip()
    
    def _extract_base_entities(self, doc) -> list[dict]:
        """Extract base entities from spaCy doc."""
        entities = []
        
        for ent in doc.ents:
            entity_type = self.LABEL_MAP.get(ent.label_)
            if not entity_type:
                continue
            
            # Get surrounding context (50 chars each side)
            start = max(0, ent.start_char - 50)
            end = min(len(doc.text), ent.end_char + 50)
            context = doc.text[start:end]
            
            entities.append({
                'name': ent.text,
                'entity_type': entity_type,
                'context': context,
                'start': ent.start_char,
                'end': ent.end_char,
            })
        
        return entities
    
    def _enhance_with_context(self, entities: list[dict], full_text: str) -> list[ExtractedEntity]:
        """Enhance entities with additional context like job titles."""
        enhanced = []
        
        for ent in entities:
            entity = ExtractedEntity(
                name=ent['name'],
                entity_type=ent['entity_type'],
                context=ent['context'],
                mentions=[{'start': ent['start'], 'end': ent['end']}]
            )
            
            # For Person entities, try to extract title and organization
            if entity.entity_type == 'Person':
                title_info = self._extract_person_title(ent['name'], ent['context'], full_text)
                if title_info:
                    entity.job_title = title_info.get('title')
                    entity.works_for = title_info.get('organization')
            
            enhanced.append(entity)
        
        return enhanced
    
    def _extract_person_title(self, name: str, context: str, full_text: str) -> Optional[dict]:
        """Extract job title and organization for a person."""
        result = {}
        
        # Search in context first, then full text
        search_texts = [context, full_text]
        
        for text in search_texts:
            for pattern in self.TITLE_PATTERNS:
                matches = re.finditer(pattern, text, re.IGNORECASE)
                for match in matches:
                    groups = match.groups()
                    # Check if this match relates to our person
                    if any(name.lower() in g.lower() for g in groups if g):
                        # Extract title
                        for g in groups:
                            if g and g.upper() in ['CEO', 'CTO', 'CFO', 'COO', 'CMO', 
                                                    'PRESIDENT', 'DIRECTOR', 'MANAGER',
                                                    'FOUNDER', 'CO-FOUNDER', 'CHAIRMAN',
                                                    'VICE PRESIDENT', 'VP']:
                                result['title'] = g
                                break
                            elif g and re.match(r'(head|chief|lead|senior|principal)', g, re.I):
                                result['title'] = match.group(0)
                                break
        
        # Try to find organization
        for pattern in self.ORG_CONTEXT_PATTERNS:
            # Search near the person's name
            name_pos = full_text.lower().find(name.lower())
            if name_pos >= 0:
                search_range = full_text[max(0, name_pos-100):name_pos+100+len(name)]
                matches = re.findall(pattern, search_range)
                if matches:
                    result['organization'] = matches[0] if isinstance(matches[0], str) else matches[0][0]
                    break
        
        return result if result else None
    
    def _deduplicate(self, entities: list[ExtractedEntity]) -> list[ExtractedEntity]:
        """Merge duplicate entities and combine their mentions."""
        seen = {}
        
        for entity in entities:
            # Create normalized key
            key = (entity.name.lower(), entity.entity_type)
            
            if key in seen:
                # Merge mentions
                seen[key].mentions.extend(entity.mentions)
                # Keep richer context
                if entity.job_title and not seen[key].job_title:
                    seen[key].job_title = entity.job_title
                if entity.works_for and not seen[key].works_for:
                    seen[key].works_for = entity.works_for
            else:
                seen[key] = entity
        
        return list(seen.values())
    
    def extract_to_json(self, text: str) -> str:
        """Extract entities and return as JSON string."""
        entities = self.extract(text)
        return json.dumps([e.to_dict() for e in entities], indent=2)


def main():
    """CLI interface for entity extraction."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Extract entities from article text')
    parser.add_argument('input', help='Input file path or - for stdin')
    parser.add_argument('-o', '--output', help='Output file path (default: stdout)')
    parser.add_argument('-m', '--model', default='en_core_web_sm',
                        help='spaCy model to use (default: en_core_web_sm)')
    parser.add_argument('--format', choices=['json', 'text'], default='json',
                        help='Output format (default: json)')
    
    args = parser.parse_args()
    
    # Read input
    if args.input == '-':
        import sys
        text = sys.stdin.read()
    else:
        text = Path(args.input).read_text()
    
    # Extract entities
    extractor = EntityExtractor(model_name=args.model)
    entities = extractor.extract(text)
    
    # Format output
    if args.format == 'json':
        output = json.dumps([e.to_dict() for e in entities], indent=2)
    else:
        lines = []
        for e in entities:
            lines.append(f"[{e.entity_type}] {e.name}")
            if e.job_title:
                lines.append(f"  Title: {e.job_title}")
            if e.works_for:
                lines.append(f"  Org: {e.works_for}")
            lines.append(f"  Mentions: {len(e.mentions)}")
            lines.append("")
        output = '\n'.join(lines)
    
    # Write output
    if args.output:
        Path(args.output).write_text(output)
    else:
        print(output)


if __name__ == '__main__':
    main()
