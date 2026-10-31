#!/usr/bin/env python3
"""
Content correction: Fix entity inconsistencies in article text.
Replaces incorrect entity references with canonical versions from library.
"""

import re
import json
from dataclasses import dataclass
from typing import Optional
from pathlib import Path


@dataclass
class Correction:
    """Represents a single correction made to the text."""
    original: str
    corrected: str
    entity_id: str
    reason: str
    position: tuple[int, int]


class ContentCorrector:
    """Correct entity references in article text."""
    
    def __init__(self, entity_library: list[dict]):
        """
        Initialize corrector with entity library.
        
        Args:
            entity_library: List of canonical entity entries
        """
        self.library = entity_library
        self._build_correction_map()
    
    def _build_correction_map(self):
        """Build map of incorrect forms to canonical forms."""
        self.corrections = {}  # alias -> (canonical, entity_id)
        self.canonical_forms = {}  # entity_id -> canonical entry
        
        for entity in self.library:
            if entity.get('status') not in ['active', 'pending_review']:
                continue
            
            entity_id = entity.get('entity_id', '')
            canonical = entity.get('canonical_name', '')
            entity_type = entity.get('entity_type', '')
            
            if not canonical or not entity_id:
                continue
            
            self.canonical_forms[entity_id] = entity
            
            # Map aliases to canonical
            aliases = entity.get('aliases', '')
            if aliases:
                for alias in aliases.split(','):
                    alias = alias.strip()
                    if alias and alias.lower() != canonical.lower():
                        self.corrections[alias.lower()] = (canonical, entity_id)
            
            # For Person entities, also correct title/org inconsistencies
            if entity_type == 'Person':
                job_title = entity.get('job_title', '')
                works_for = entity.get('works_for', '')
                
                # Store full canonical form
                if job_title and works_for:
                    full_form = f"{canonical}, {job_title} of {works_for}"
                elif job_title:
                    full_form = f"{canonical}, {job_title}"
                else:
                    full_form = canonical
                
                entity['_full_form'] = full_form
    
    def correct(self, text: str, match_results: list[dict]) -> tuple[str, list[Correction]]:
        """
        Apply corrections to text based on match results.
        
        Args:
            text: Original article text
            match_results: Results from EntityMatcher.match_all()
            
        Returns:
            Tuple of (corrected_text, list_of_corrections)
        """
        corrections_made = []
        corrected_text = text
        offset = 0  # Track position shift from prior corrections
        
        for result in match_results:
            if result.get('action') == 'use_existing' and result.get('conflicts'):
                # Entity exists but has conflicts - need to correct
                corrections = self._correct_conflicts(
                    corrected_text,
                    result['extracted_name'],
                    result['matched_entity_id'],
                    result['conflicts'],
                )
                
                for corr in corrections:
                    corrected_text, new_offset = self._apply_correction(
                        corrected_text, corr, offset
                    )
                    offset = new_offset
                    corrections_made.append(corr)
            
            elif result.get('action') in ['auto_add_active', 'auto_add_pending']:
                # New entity - no corrections needed for the name itself
                # But we might want to enhance the text with additional context
                pass
        
        # Also correct any alias usages to canonical forms
        for alias, (canonical, entity_id) in self.corrections.items():
            pattern = r'\b' + re.escape(alias) + r'\b'
            matches = list(re.finditer(pattern, corrected_text, re.IGNORECASE))
            
            for match in reversed(matches):  # Reverse to maintain positions
                # Check if already canonical
                if match.group().lower() == canonical.lower():
                    continue
                
                corr = Correction(
                    original=match.group(),
                    corrected=canonical,
                    entity_id=entity_id,
                    reason='alias_to_canonical',
                    position=(match.start(), match.end()),
                )
                
                corrected_text = (
                    corrected_text[:match.start()] +
                    canonical +
                    corrected_text[match.end():]
                )
                corrections_made.append(corr)
        
        return corrected_text, corrections_made
    
    def _correct_conflicts(self, text: str, name: str, entity_id: str,
                          conflicts: list[dict]) -> list[Correction]:
        """Generate corrections for conflicting entity details."""
        corrections = []
        entity = self.canonical_forms.get(entity_id)
        
        if not entity:
            return corrections
        
        for conflict in conflicts:
            field = conflict['field']
            extracted = conflict['extracted']
            library_val = conflict['library']
            
            if field == 'job_title':
                # Find and correct title mentions
                # Pattern: "Name, <wrong title>"
                pattern = rf'\b{re.escape(name)}\s*,\s*{re.escape(extracted)}\b'
                match = re.search(pattern, text, re.IGNORECASE)
                
                if match:
                    corrected = f"{name}, {library_val}"
                    corrections.append(Correction(
                        original=match.group(),
                        corrected=corrected,
                        entity_id=entity_id,
                        reason=f'title_conflict: {extracted} -> {library_val}',
                        position=(match.start(), match.end()),
                    ))
            
            elif field == 'works_for':
                # Find and correct organization mentions
                # Pattern: "<wrong title> at/of <wrong org>"
                pattern = rf'\b{re.escape(name)}[^.]*(?:at|of|with)\s+{re.escape(extracted)}\b'
                match = re.search(pattern, text, re.IGNORECASE)
                
                if match:
                    corrected = match.group().replace(extracted, library_val)
                    corrections.append(Correction(
                        original=match.group(),
                        corrected=corrected,
                        entity_id=entity_id,
                        reason=f'org_conflict: {extracted} -> {library_val}',
                        position=(match.start(), match.end()),
                    ))
        
        return corrections
    
    def _apply_correction(self, text: str, correction: Correction,
                         offset: int) -> tuple[str, int]:
        """Apply a single correction and return new text and offset."""
        start, end = correction.position
        start += offset
        end += offset
        
        new_text = text[:start] + correction.corrected + text[end:]
        new_offset = offset + (len(correction.corrected) - len(correction.original))
        
        return new_text, new_offset
    
    def enhance_first_mention(self, text: str, entity_id: str) -> str:
        """
        Enhance first mention of an entity with full context.
        E.g., "John" becomes "John Smith, CEO of Acme Corp"
        """
        entity = self.canonical_forms.get(entity_id)
        if not entity:
            return text
        
        canonical = entity.get('canonical_name', '')
        full_form = entity.get('_full_form', canonical)
        
        if canonical == full_form:
            return text
        
        # Find first mention and enhance
        pattern = r'\b' + re.escape(canonical) + r'\b'
        match = re.search(pattern, text)
        
        if match:
            # Check if already has title/context after it
            after_text = text[match.end():match.end()+50]
            if re.match(r'\s*,\s*\w+', after_text):
                # Already has context, don't double-add
                return text
            
            text = text[:match.start()] + full_form + text[match.end():]
        
        return text


def correct_article(article_text: str, 
                   entity_library: list[dict],
                   match_results: list[dict]) -> dict:
    """
    Main function to correct an article.
    
    Args:
        article_text: Original markdown article
        entity_library: Entity library entries
        match_results: Results from entity matching
        
    Returns:
        Dict with corrected_text, corrections list, and summary
    """
    corrector = ContentCorrector(entity_library)
    
    corrected_text, corrections = corrector.correct(article_text, match_results)
    
    # Optionally enhance first mentions of key entities
    for result in match_results:
        if result.get('action') == 'use_existing':
            corrected_text = corrector.enhance_first_mention(
                corrected_text, 
                result['matched_entity_id']
            )
    
    return {
        'corrected_text': corrected_text,
        'corrections': [
            {
                'original': c.original,
                'corrected': c.corrected,
                'entity_id': c.entity_id,
                'reason': c.reason,
            }
            for c in corrections
        ],
        'summary': {
            'total_corrections': len(corrections),
            'by_reason': _count_by_reason(corrections),
        }
    }


def _count_by_reason(corrections: list[Correction]) -> dict:
    """Count corrections by reason type."""
    counts = {}
    for c in corrections:
        reason_type = c.reason.split(':')[0]
        counts[reason_type] = counts.get(reason_type, 0) + 1
    return counts


def main():
    """CLI interface for content correction."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Correct entity references in article')
    parser.add_argument('article', help='Markdown article file')
    parser.add_argument('library', help='JSON file with entity library')
    parser.add_argument('matches', help='JSON file with match results')
    parser.add_argument('-o', '--output', help='Output file for corrected article')
    parser.add_argument('--report', help='Output file for correction report')
    
    args = parser.parse_args()
    
    # Load data
    article_text = Path(args.article).read_text()
    library = json.loads(Path(args.library).read_text())
    matches = json.loads(Path(args.matches).read_text())
    
    # Apply corrections
    result = correct_article(article_text, library, matches)
    
    # Output corrected article
    if args.output:
        Path(args.output).write_text(result['corrected_text'])
    else:
        print(result['corrected_text'])
    
    # Output report
    if args.report:
        report = {
            'corrections': result['corrections'],
            'summary': result['summary'],
        }
        Path(args.report).write_text(json.dumps(report, indent=2))
    
    # Print summary to stderr
    import sys
    print(f"\nCorrections applied: {result['summary']['total_corrections']}", file=sys.stderr)
    for reason, count in result['summary']['by_reason'].items():
        print(f"  {reason}: {count}", file=sys.stderr)


if __name__ == '__main__':
    main()
