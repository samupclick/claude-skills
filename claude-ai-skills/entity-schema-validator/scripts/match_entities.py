#!/usr/bin/env python3
"""
Entity matching against library with confidence scoring.
Matches extracted entities to canonical entries and calculates confidence.
"""

import re
import json
from dataclasses import dataclass, field, asdict
from typing import Optional
from pathlib import Path
from difflib import SequenceMatcher


@dataclass
class MatchResult:
    """Result of matching an extracted entity to the library."""
    extracted_name: str
    extracted_type: str
    matched_entity_id: Optional[str] = None
    matched_name: Optional[str] = None
    confidence_score: int = 0
    confidence_factors: dict = field(default_factory=dict)
    classification: str = "low"  # high, medium, low
    action: str = "log_only"  # auto_add_active, auto_add_pending, log_only, use_existing
    suggested_entry: Optional[dict] = None
    conflicts: list = field(default_factory=list)
    
    def to_dict(self):
        return asdict(self)


class EntityMatcher:
    """Match extracted entities against library and site content."""
    
    DEFAULT_WEIGHTS = {
        'exact_site_match': 30,
        'partial_site_match': 15,
        'consistent_context': 20,
        'linked_entity': 15,
        'structured_data_found': 10,
        'web_corroboration': 10,
    }
    
    DEFAULT_THRESHOLDS = {
        'auto_add_active': 85,
        'auto_add_pending': 60,
        'minimum_for_schema': 60,
    }
    
    def __init__(self, 
                 entity_library: list[dict],
                 site_index: Optional[list[dict]] = None,
                 weights: Optional[dict] = None,
                 thresholds: Optional[dict] = None):
        """
        Initialize matcher.
        
        Args:
            entity_library: List of entity dicts from Google Sheets
            site_index: List of indexed site pages with text content
            weights: Custom confidence factor weights
            thresholds: Custom confidence thresholds
        """
        self.library = entity_library
        self.site_index = site_index or []
        self.weights = {**self.DEFAULT_WEIGHTS, **(weights or {})}
        self.thresholds = {**self.DEFAULT_THRESHOLDS, **(thresholds or {})}
        
        # Build lookup indexes
        self._build_indexes()
    
    def _build_indexes(self):
        """Build fast lookup indexes for the library."""
        self.by_name = {}
        self.by_alias = {}
        self.by_id = {}
        
        for entity in self.library:
            entity_id = entity.get('entity_id', '')
            canonical = entity.get('canonical_name', '').lower()
            
            self.by_id[entity_id] = entity
            self.by_name[canonical] = entity
            
            # Index aliases
            aliases = entity.get('aliases', '')
            if aliases:
                for alias in aliases.split(','):
                    alias = alias.strip().lower()
                    if alias:
                        self.by_alias[alias] = entity
    
    def match(self, extracted_entity: dict) -> MatchResult:
        """
        Match an extracted entity against the library.
        
        Args:
            extracted_entity: Dict with name, entity_type, context, etc.
            
        Returns:
            MatchResult with confidence score and recommended action
        """
        name = extracted_entity.get('name', '')
        entity_type = extracted_entity.get('entity_type', '')
        context = extracted_entity.get('context', '')
        job_title = extracted_entity.get('job_title')
        works_for = extracted_entity.get('works_for')
        
        result = MatchResult(
            extracted_name=name,
            extracted_type=entity_type,
        )
        
        # Step 1: Try exact match in library
        library_match = self._find_library_match(name, entity_type)
        
        if library_match:
            result.matched_entity_id = library_match.get('entity_id')
            result.matched_name = library_match.get('canonical_name')
            result.action = 'use_existing'
            result.confidence_score = 100
            result.classification = 'high'
            result.confidence_factors = {'library_match': 100}
            
            # Check for conflicts
            conflicts = self._check_conflicts(extracted_entity, library_match)
            if conflicts:
                result.conflicts = conflicts
            
            return result
        
        # Step 2: Calculate confidence for new entity
        factors = self._calculate_confidence_factors(extracted_entity)
        result.confidence_factors = factors
        
        # Sum factors (max 100)
        total = min(sum(factors.values()), 100)
        result.confidence_score = total
        
        # Classify and determine action
        if total >= self.thresholds['auto_add_active']:
            result.classification = 'high'
            result.action = 'auto_add_active'
        elif total >= self.thresholds['auto_add_pending']:
            result.classification = 'medium'
            result.action = 'auto_add_pending'
        else:
            result.classification = 'low'
            result.action = 'log_only'
        
        # Generate suggested entry
        result.suggested_entry = self._generate_suggested_entry(extracted_entity, factors)
        
        return result
    
    def _find_library_match(self, name: str, entity_type: str) -> Optional[dict]:
        """Find matching entity in library by name or alias."""
        name_lower = name.lower()
        
        # Exact name match
        if name_lower in self.by_name:
            match = self.by_name[name_lower]
            if match.get('entity_type') == entity_type:
                return match
        
        # Alias match
        if name_lower in self.by_alias:
            match = self.by_alias[name_lower]
            if match.get('entity_type') == entity_type:
                return match
        
        # Fuzzy match for close names
        for canonical, entity in self.by_name.items():
            if entity.get('entity_type') != entity_type:
                continue
            similarity = SequenceMatcher(None, name_lower, canonical).ratio()
            if similarity > 0.85:
                return entity
        
        return None
    
    def _calculate_confidence_factors(self, entity: dict) -> dict:
        """Calculate individual confidence factors."""
        factors = {}
        name = entity.get('name', '')
        
        # Factor 1: Exact site match
        exact_match = self._check_exact_site_match(name)
        if exact_match:
            factors['exact_site_match'] = self.weights['exact_site_match']
        
        # Factor 2: Partial site match (only if no exact match)
        if 'exact_site_match' not in factors:
            partial_match = self._check_partial_site_match(name)
            if partial_match:
                factors['partial_site_match'] = self.weights['partial_site_match']
        
        # Factor 3: Consistent context
        consistency = self._check_consistent_context(entity)
        if consistency:
            factors['consistent_context'] = consistency
        
        # Factor 4: Linked entity
        if self._check_linked_entity(entity):
            factors['linked_entity'] = self.weights['linked_entity']
        
        # Factor 5: Structured data
        if self._check_structured_data(name):
            factors['structured_data_found'] = self.weights['structured_data_found']
        
        # Factor 6: Web corroboration (placeholder - would need web search integration)
        # factors['web_corroboration'] = 0
        
        return factors
    
    def _check_exact_site_match(self, name: str) -> bool:
        """Check if entity name appears exactly in site content."""
        name_lower = name.lower()
        
        for page in self.site_index:
            text = page.get('text', '').lower()
            
            # Check for standalone mention (not substring of another word)
            pattern = r'\b' + re.escape(name_lower) + r'\b'
            if re.search(pattern, text):
                return True
        
        return False
    
    def _check_partial_site_match(self, name: str) -> bool:
        """Check if similar name/variant appears on site."""
        variants = self._generate_name_variants(name)
        
        for page in self.site_index:
            text = page.get('text', '').lower()
            for variant in variants:
                pattern = r'\b' + re.escape(variant.lower()) + r'\b'
                if re.search(pattern, text):
                    return True
        
        return False
    
    def _generate_name_variants(self, name: str) -> list[str]:
        """Generate common name variants."""
        variants = []
        parts = name.split()
        
        if len(parts) >= 2:
            # First initial + last name
            variants.append(f"{parts[0][0]}. {parts[-1]}")
            # First name + last initial
            variants.append(f"{parts[0]} {parts[-1][0]}.")
            # Just first name
            variants.append(parts[0])
            # Just last name
            variants.append(parts[-1])
        
        # Common title variations
        name_lower = name.lower()
        if 'corporation' in name_lower:
            variants.append(name.replace('Corporation', 'Corp').replace('corporation', 'corp'))
        if 'corp' in name_lower and 'corporation' not in name_lower:
            variants.append(name.replace('Corp', 'Corporation').replace('corp', 'corporation'))
        if 'incorporated' in name_lower:
            variants.append(name.replace('Incorporated', 'Inc').replace('incorporated', 'inc'))
        
        return variants
    
    def _check_consistent_context(self, entity: dict) -> int:
        """Check if entity details are consistent across sources."""
        name = entity.get('name', '').lower()
        job_title = entity.get('job_title', '').lower() if entity.get('job_title') else None
        works_for = entity.get('works_for', '').lower() if entity.get('works_for') else None
        
        mentions_with_context = []
        
        for page in self.site_index:
            text = page.get('text', '').lower()
            if name in text:
                # Extract surrounding context
                pos = text.find(name)
                context = text[max(0, pos-100):pos+len(name)+100]
                mentions_with_context.append(context)
        
        if len(mentions_with_context) < 2:
            return 0
        
        # Check if contexts agree
        agreements = 0
        checks = 0
        
        if job_title:
            title_mentions = sum(1 for ctx in mentions_with_context if job_title in ctx)
            if title_mentions >= 2:
                agreements += 1
            checks += 1
        
        if works_for:
            org_mentions = sum(1 for ctx in mentions_with_context if works_for in ctx)
            if org_mentions >= 2:
                agreements += 1
            checks += 1
        
        if checks == 0:
            # No specific details to verify, but multiple mentions exist
            return self.weights['consistent_context'] // 2
        
        agreement_ratio = agreements / checks
        if agreement_ratio >= 0.8:
            return self.weights['consistent_context']
        elif agreement_ratio >= 0.5:
            return self.weights['consistent_context'] // 2
        
        return 0
    
    def _check_linked_entity(self, entity: dict) -> bool:
        """Check if entity references known entities in library."""
        works_for = entity.get('works_for', '')
        
        if works_for:
            works_for_lower = works_for.lower()
            if works_for_lower in self.by_name or works_for_lower in self.by_alias:
                return True
        
        return False
    
    def _check_structured_data(self, name: str) -> bool:
        """Check if entity appears in existing JSON-LD on site."""
        name_lower = name.lower()
        
        for page in self.site_index:
            schemas = page.get('json_ld', [])
            for schema in schemas:
                schema_str = json.dumps(schema).lower()
                if name_lower in schema_str:
                    return True
        
        return False
    
    def _check_conflicts(self, extracted: dict, library_entry: dict) -> list[dict]:
        """Check for conflicts between extracted entity and library entry."""
        conflicts = []
        
        # Check job title
        extracted_title = extracted.get('job_title', '')
        library_title = library_entry.get('job_title', '')
        if extracted_title and library_title:
            if extracted_title.lower() != library_title.lower():
                conflicts.append({
                    'field': 'job_title',
                    'extracted': extracted_title,
                    'library': library_title,
                })
        
        # Check organization
        extracted_org = extracted.get('works_for', '')
        library_org = library_entry.get('works_for', '')
        if extracted_org and library_org:
            if extracted_org.lower() != library_org.lower():
                conflicts.append({
                    'field': 'works_for',
                    'extracted': extracted_org,
                    'library': library_org,
                })
        
        return conflicts
    
    def _generate_suggested_entry(self, entity: dict, factors: dict) -> dict:
        """Generate a suggested library entry for a new entity."""
        name = entity.get('name', '')
        entity_type = entity.get('entity_type', '')
        
        # Generate entity_id
        slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
        entity_id = f"{entity_type.lower()}-{slug}"
        
        entry = {
            'entity_id': entity_id,
            'entity_type': entity_type,
            'canonical_name': name,
            'aliases': '',
            'description': '',  # Needs to be filled
            'status': 'pending_review',
        }
        
        # Add type-specific fields
        if entity_type == 'Person':
            entry['job_title'] = entity.get('job_title', '')
            entry['works_for'] = entity.get('works_for', '')
        
        return entry
    
    def match_all(self, extracted_entities: list[dict]) -> list[MatchResult]:
        """Match all extracted entities."""
        return [self.match(e) for e in extracted_entities]


def main():
    """CLI interface for entity matching."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Match entities against library')
    parser.add_argument('entities', help='JSON file with extracted entities')
    parser.add_argument('library', help='JSON file with entity library')
    parser.add_argument('-s', '--site-index', help='JSON file with site index')
    parser.add_argument('-o', '--output', help='Output file path')
    parser.add_argument('-c', '--config', help='Config file with weights/thresholds')
    
    args = parser.parse_args()
    
    # Load data
    entities = json.loads(Path(args.entities).read_text())
    library = json.loads(Path(args.library).read_text())
    
    site_index = []
    if args.site_index:
        site_index = json.loads(Path(args.site_index).read_text())
    
    weights = None
    thresholds = None
    if args.config:
        config = json.loads(Path(args.config).read_text())
        weights = config.get('factor_weights')
        thresholds = config.get('confidence_thresholds')
    
    # Match entities
    matcher = EntityMatcher(
        entity_library=library,
        site_index=site_index,
        weights=weights,
        thresholds=thresholds,
    )
    
    results = matcher.match_all(entities)
    
    # Output
    output = json.dumps([r.to_dict() for r in results], indent=2)
    
    if args.output:
        Path(args.output).write_text(output)
    else:
        print(output)


if __name__ == '__main__':
    main()
