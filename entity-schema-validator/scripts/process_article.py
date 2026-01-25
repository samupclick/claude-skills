#!/usr/bin/env python3
"""
Process article: Full pipeline for entity validation and schema generation.
Orchestrates extraction, matching, correction, and schema generation.
"""

import json
import re
import yaml
from datetime import datetime
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, asdict

from extract_entities import EntityExtractor
from match_entities import EntityMatcher
from correct_content import correct_article
from generate_schema import generate_schema, SchemaGenerator


@dataclass
class ProcessingResult:
    """Result of processing an article."""
    original_article: str
    corrected_article: str
    schema: dict
    validation_report: dict
    output_markdown: str
    
    def to_dict(self):
        return asdict(self)


def load_config(config_path: Path) -> dict:
    """Load client configuration."""
    return json.loads(config_path.read_text())


def process_article(
    article_path: Path,
    library_path: Path,
    site_index_path: Optional[Path] = None,
    config_path: Optional[Path] = None,
    output_dir: Optional[Path] = None,
    spacy_model: str = "en_core_web_sm"
) -> ProcessingResult:
    """
    Process a single article through the full pipeline.
    
    Args:
        article_path: Path to markdown article
        library_path: Path to entity library JSON
        site_index_path: Path to site index JSON (optional)
        config_path: Path to client config (optional)
        output_dir: Directory for outputs (optional)
        spacy_model: spaCy model to use
        
    Returns:
        ProcessingResult with all outputs
    """
    # Load inputs
    article_text = article_path.read_text()
    library = json.loads(library_path.read_text())
    
    site_index = []
    if site_index_path and site_index_path.exists():
        site_index = json.loads(site_index_path.read_text())
    
    config = {}
    if config_path and config_path.exists():
        config = load_config(config_path)
    
    weights = config.get('factor_weights')
    thresholds = config.get('confidence_thresholds')
    
    # Step 1: Extract entities
    print("Step 1: Extracting entities...")
    extractor = EntityExtractor(model_name=spacy_model)
    extracted = extractor.extract(article_text)
    extracted_dicts = [e.to_dict() for e in extracted]
    print(f"  Found {len(extracted)} entities")
    
    # Step 2: Match against library
    print("Step 2: Matching against library...")
    matcher = EntityMatcher(
        entity_library=library,
        site_index=site_index,
        weights=weights,
        thresholds=thresholds,
    )
    match_results = matcher.match_all(extracted_dicts)
    match_dicts = [m.to_dict() for m in match_results]
    
    # Categorize results
    existing = [m for m in match_dicts if m['action'] == 'use_existing']
    auto_added = [m for m in match_dicts if m['action'] in ['auto_add_active', 'auto_add_pending']]
    low_conf = [m for m in match_dicts if m['action'] == 'log_only']
    conflicts = [m for m in match_dicts if m.get('conflicts')]
    
    print(f"  Matched to library: {len(existing)}")
    print(f"  Auto-added: {len(auto_added)}")
    print(f"  Low confidence: {len(low_conf)}")
    print(f"  Conflicts found: {len(conflicts)}")
    
    # Step 3: Correct content
    print("Step 3: Correcting content...")
    correction_result = correct_article(article_text, library, match_dicts)
    corrected_text = correction_result['corrected_text']
    print(f"  Corrections made: {correction_result['summary']['total_corrections']}")
    
    # Step 4: Generate schema
    print("Step 4: Generating schema...")
    
    # Extract article metadata
    article_title = None
    h1_match = re.search(r'^#\s+(.+)$', article_text, re.MULTILINE)
    if h1_match:
        article_title = h1_match.group(1).strip()
    
    article_date = datetime.utcnow().strftime('%Y-%m-%d')
    publisher_id = config.get('publisher_entity_id')
    min_confidence = thresholds.get('minimum_for_schema', 60) if thresholds else 60
    
    schema = generate_schema(
        article_text=corrected_text,
        entity_library=library + [m['suggested_entry'] for m in auto_added if m.get('suggested_entry')],
        match_results=match_dicts,
        article_title=article_title,
        article_date=article_date,
        publisher_id=publisher_id,
        minimum_confidence=min_confidence,
    )
    
    schema_count = len(schema.get('@graph', [])) - 1  # Minus Article itself
    print(f"  Schema entities: {schema_count}")
    
    # Step 5: Generate validation report
    print("Step 5: Generating report...")
    report = generate_validation_report(
        article_path.name,
        extracted_dicts,
        match_dicts,
        correction_result,
        schema,
    )
    
    # Step 6: Generate output markdown with frontmatter
    output_markdown = generate_output_markdown(
        corrected_text,
        schema,
        report,
    )
    
    # Save outputs if output_dir provided
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        
        stem = article_path.stem
        
        # Corrected article
        (output_dir / f"{stem}_corrected.md").write_text(output_markdown)
        
        # Schema JSON
        (output_dir / f"{stem}_schema.json").write_text(
            json.dumps(schema, indent=2)
        )
        
        # Validation report
        (output_dir / f"{stem}_report.json").write_text(
            json.dumps(report, indent=2)
        )
        
        print(f"\nOutputs saved to {output_dir}/")
    
    return ProcessingResult(
        original_article=article_text,
        corrected_article=corrected_text,
        schema=schema,
        validation_report=report,
        output_markdown=output_markdown,
    )


def generate_validation_report(
    article_name: str,
    extracted: list[dict],
    matches: list[dict],
    corrections: dict,
    schema: dict,
) -> dict:
    """Generate validation report for the article."""
    
    # Categorize matches
    existing = [m for m in matches if m['action'] == 'use_existing']
    auto_active = [m for m in matches if m['action'] == 'auto_add_active']
    auto_pending = [m for m in matches if m['action'] == 'auto_add_pending']
    low_conf = [m for m in matches if m['action'] == 'log_only']
    conflicts = [m for m in matches if m.get('conflicts')]
    
    # Calculate average confidence
    scores = [m['confidence_score'] for m in matches]
    avg_confidence = sum(scores) / len(scores) if scores else 0
    
    return {
        'article': article_name,
        'processed_at': datetime.utcnow().isoformat(),
        'summary': {
            'entities_found': len(extracted),
            'matched_to_library': len(existing),
            'auto_added_active': len(auto_active),
            'auto_added_pending': len(auto_pending),
            'low_confidence': len(low_conf),
            'conflicts_detected': len(conflicts),
            'corrections_made': corrections['summary']['total_corrections'],
            'schema_entities': len(schema.get('@graph', [])) - 1,
            'average_confidence': round(avg_confidence, 1),
        },
        'entities': {
            'matched': [
                {'name': m['extracted_name'], 'entity_id': m['matched_entity_id']}
                for m in existing
            ],
            'auto_added': [
                {
                    'name': m['extracted_name'],
                    'confidence': m['confidence_score'],
                    'status': 'active' if m['action'] == 'auto_add_active' else 'pending_review',
                    'suggested_id': m.get('suggested_entry', {}).get('entity_id'),
                }
                for m in auto_active + auto_pending
            ],
            'low_confidence': [
                {
                    'name': m['extracted_name'],
                    'confidence': m['confidence_score'],
                    'factors': m['confidence_factors'],
                }
                for m in low_conf
            ],
            'conflicts': [
                {
                    'name': m['extracted_name'],
                    'entity_id': m['matched_entity_id'],
                    'conflicts': m['conflicts'],
                }
                for m in conflicts
            ],
        },
        'corrections': corrections['corrections'],
    }


def generate_output_markdown(
    corrected_text: str,
    schema: dict,
    report: dict,
) -> str:
    """Generate final markdown with YAML frontmatter."""
    
    # Build frontmatter
    frontmatter = {
        'schema': schema,
        'validation': {
            'entities_found': report['summary']['entities_found'],
            'matched': report['summary']['matched_to_library'],
            'auto_added': report['summary']['auto_added_active'] + report['summary']['auto_added_pending'],
            'pending_review': report['summary']['auto_added_pending'],
            'low_confidence': report['summary']['low_confidence'],
            'confidence_avg': report['summary']['average_confidence'],
        },
        'processed_at': report['processed_at'],
    }
    
    # Convert to YAML
    yaml_str = yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True)
    
    # Combine
    output = f"---\n{yaml_str}---\n\n{corrected_text}"
    
    return output


def main():
    """CLI interface for article processing."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Process article through entity validation pipeline')
    parser.add_argument('article', help='Markdown article file')
    parser.add_argument('library', help='Entity library JSON file')
    parser.add_argument('-s', '--site-index', help='Site index JSON file')
    parser.add_argument('-c', '--config', help='Client config JSON file')
    parser.add_argument('-o', '--output-dir', help='Output directory')
    parser.add_argument('-m', '--model', default='en_core_web_sm',
                        help='spaCy model (default: en_core_web_sm)')
    parser.add_argument('--json', action='store_true',
                        help='Output full result as JSON')
    
    args = parser.parse_args()
    
    result = process_article(
        article_path=Path(args.article),
        library_path=Path(args.library),
        site_index_path=Path(args.site_index) if args.site_index else None,
        config_path=Path(args.config) if args.config else None,
        output_dir=Path(args.output_dir) if args.output_dir else None,
        spacy_model=args.model,
    )
    
    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print("\n" + "="*60)
        print("PROCESSING COMPLETE")
        print("="*60)
        print(f"\nSummary:")
        for key, value in result.validation_report['summary'].items():
            print(f"  {key}: {value}")
        
        if not args.output_dir:
            print("\n" + "-"*60)
            print("CORRECTED ARTICLE:")
            print("-"*60)
            print(result.output_markdown[:2000])
            if len(result.output_markdown) > 2000:
                print("\n... (truncated)")


if __name__ == '__main__':
    main()
