#!/usr/bin/env python3
"""
Google Sheets sync: Read/write entity library to Google Sheets.
Handles the Active Entities, Pending Review, and Audit Log tabs.
"""

import json
from datetime import datetime
from typing import Optional
from pathlib import Path

try:
    import gspread
    from google.oauth2.service_account import Credentials
except ImportError:
    gspread = None
    Credentials = None


# Required columns for each tab
ACTIVE_ENTITIES_COLUMNS = [
    'entity_id', 'entity_type', 'canonical_name', 'aliases', 'description',
    'url', 'image_url', 'job_title', 'works_for', 'same_as',
    'last_verified', 'status'
]

PENDING_REVIEW_COLUMNS = [
    'entity_id', 'entity_type', 'canonical_name', 'extracted_from',
    'confidence_score', 'suggested_entry', 'date_added', 'reviewer_action', 'notes'
]

AUDIT_LOG_COLUMNS = [
    'timestamp', 'action', 'entity_id', 'changes', 'source_article', 'confidence'
]


class EntityLibrarySync:
    """Sync entity library with Google Sheets."""
    
    SCOPES = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive.readonly'
    ]
    
    def __init__(self, credentials_path: str, spreadsheet_url: str):
        """
        Initialize sync.
        
        Args:
            credentials_path: Path to service account JSON
            spreadsheet_url: Google Sheets URL
        """
        if gspread is None:
            raise ImportError("gspread required. Install with: pip install gspread google-auth")
        
        creds = Credentials.from_service_account_file(
            credentials_path, scopes=self.SCOPES
        )
        self.client = gspread.authorize(creds)
        self.spreadsheet = self.client.open_by_url(spreadsheet_url)
        
        self._ensure_tabs_exist()
    
    def _ensure_tabs_exist(self):
        """Ensure required tabs exist with correct headers."""
        existing = [ws.title for ws in self.spreadsheet.worksheets()]
        
        if 'Active Entities' not in existing:
            ws = self.spreadsheet.add_worksheet('Active Entities', rows=1000, cols=20)
            ws.append_row(ACTIVE_ENTITIES_COLUMNS)
        
        if 'Pending Review' not in existing:
            ws = self.spreadsheet.add_worksheet('Pending Review', rows=1000, cols=15)
            ws.append_row(PENDING_REVIEW_COLUMNS)
        
        if 'Audit Log' not in existing:
            ws = self.spreadsheet.add_worksheet('Audit Log', rows=5000, cols=10)
            ws.append_row(AUDIT_LOG_COLUMNS)
    
    def read_library(self) -> list[dict]:
        """Read all active entities from library."""
        ws = self.spreadsheet.worksheet('Active Entities')
        records = ws.get_all_records()
        return records
    
    def read_pending(self) -> list[dict]:
        """Read pending review items."""
        ws = self.spreadsheet.worksheet('Pending Review')
        records = ws.get_all_records()
        return records
    
    def add_entity(self, entity: dict, status: str = 'active',
                   source_article: str = '', confidence: int = 0):
        """
        Add new entity to library.
        
        Args:
            entity: Entity dict with required fields
            status: 'active' or 'pending_review'
            source_article: Article that triggered the addition
            confidence: Confidence score
        """
        entity['status'] = status
        entity['last_verified'] = datetime.utcnow().strftime('%Y-%m-%d')
        
        ws = self.spreadsheet.worksheet('Active Entities')
        row = [entity.get(col, '') for col in ACTIVE_ENTITIES_COLUMNS]
        ws.append_row(row)
        
        self._log_action('add', entity['entity_id'], 
                        {'status': status}, source_article, confidence)
    
    def update_entity(self, entity_id: str, updates: dict,
                     source_article: str = ''):
        """
        Update existing entity.
        
        Args:
            entity_id: Entity to update
            updates: Dict of field updates
            source_article: Article that triggered the update
        """
        ws = self.spreadsheet.worksheet('Active Entities')
        
        # Find row
        cell = ws.find(entity_id, in_column=1)
        if not cell:
            raise ValueError(f"Entity not found: {entity_id}")
        
        row_num = cell.row
        
        # Apply updates
        for field, value in updates.items():
            if field in ACTIVE_ENTITIES_COLUMNS:
                col_num = ACTIVE_ENTITIES_COLUMNS.index(field) + 1
                ws.update_cell(row_num, col_num, value)
        
        # Update last_verified
        verified_col = ACTIVE_ENTITIES_COLUMNS.index('last_verified') + 1
        ws.update_cell(row_num, verified_col, datetime.utcnow().strftime('%Y-%m-%d'))
        
        self._log_action('update', entity_id, updates, source_article, 100)
    
    def add_to_pending(self, entity: dict, source_article: str,
                      confidence: int, suggested_entry: dict):
        """
        Add entity to pending review queue.
        
        Args:
            entity: Extracted entity info
            source_article: Article filename
            confidence: Confidence score
            suggested_entry: Full suggested library entry
        """
        ws = self.spreadsheet.worksheet('Pending Review')
        
        row = [
            suggested_entry.get('entity_id', ''),
            suggested_entry.get('entity_type', ''),
            suggested_entry.get('canonical_name', ''),
            source_article,
            confidence,
            json.dumps(suggested_entry),
            datetime.utcnow().strftime('%Y-%m-%d %H:%M'),
            '',  # reviewer_action
            '',  # notes
        ]
        
        ws.append_row(row)
    
    def approve_pending(self, entity_id: str, reviewer_notes: str = ''):
        """
        Approve pending entity and move to active.
        
        Args:
            entity_id: Entity to approve
            reviewer_notes: Optional notes
        """
        pending_ws = self.spreadsheet.worksheet('Pending Review')
        active_ws = self.spreadsheet.worksheet('Active Entities')
        
        # Find in pending
        cell = pending_ws.find(entity_id, in_column=1)
        if not cell:
            raise ValueError(f"Entity not found in pending: {entity_id}")
        
        row = pending_ws.row_values(cell.row)
        suggested = json.loads(row[5])  # suggested_entry column
        
        # Add to active
        suggested['status'] = 'active'
        suggested['last_verified'] = datetime.utcnow().strftime('%Y-%m-%d')
        
        active_row = [suggested.get(col, '') for col in ACTIVE_ENTITIES_COLUMNS]
        active_ws.append_row(active_row)
        
        # Mark as approved in pending
        action_col = PENDING_REVIEW_COLUMNS.index('reviewer_action') + 1
        notes_col = PENDING_REVIEW_COLUMNS.index('notes') + 1
        pending_ws.update_cell(cell.row, action_col, 'approved')
        if reviewer_notes:
            pending_ws.update_cell(cell.row, notes_col, reviewer_notes)
        
        self._log_action('approve', entity_id, {'from': 'pending'}, '', 100)
    
    def reject_pending(self, entity_id: str, reason: str = ''):
        """Reject pending entity."""
        ws = self.spreadsheet.worksheet('Pending Review')
        
        cell = ws.find(entity_id, in_column=1)
        if not cell:
            raise ValueError(f"Entity not found in pending: {entity_id}")
        
        action_col = PENDING_REVIEW_COLUMNS.index('reviewer_action') + 1
        notes_col = PENDING_REVIEW_COLUMNS.index('notes') + 1
        ws.update_cell(cell.row, action_col, 'rejected')
        if reason:
            ws.update_cell(cell.row, notes_col, reason)
        
        self._log_action('reject', entity_id, {'reason': reason}, '', 0)
    
    def mark_stale(self, entity_ids: list[str]):
        """Mark entities as stale."""
        ws = self.spreadsheet.worksheet('Active Entities')
        status_col = ACTIVE_ENTITIES_COLUMNS.index('status') + 1
        
        for entity_id in entity_ids:
            cell = ws.find(entity_id, in_column=1)
            if cell:
                ws.update_cell(cell.row, status_col, 'stale')
                self._log_action('mark_stale', entity_id, {}, '', 0)
    
    def _log_action(self, action: str, entity_id: str, changes: dict,
                   source_article: str, confidence: int):
        """Log action to audit log."""
        ws = self.spreadsheet.worksheet('Audit Log')
        
        row = [
            datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
            action,
            entity_id,
            json.dumps(changes),
            source_article,
            confidence,
        ]
        
        ws.append_row(row)
    
    def export_to_json(self, output_path: Path):
        """Export library to JSON for offline use."""
        data = {
            'active_entities': self.read_library(),
            'pending_review': self.read_pending(),
            'exported_at': datetime.utcnow().isoformat(),
        }
        output_path.write_text(json.dumps(data, indent=2))
    
    def get_stats(self) -> dict:
        """Get library statistics."""
        entities = self.read_library()
        pending = self.read_pending()
        
        by_status = {}
        by_type = {}
        
        for e in entities:
            status = e.get('status', 'unknown')
            etype = e.get('entity_type', 'unknown')
            by_status[status] = by_status.get(status, 0) + 1
            by_type[etype] = by_type.get(etype, 0) + 1
        
        return {
            'total_entities': len(entities),
            'pending_review': len([p for p in pending if not p.get('reviewer_action')]),
            'by_status': by_status,
            'by_type': by_type,
        }


def main():
    """CLI interface for library sync."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Sync entity library with Google Sheets')
    parser.add_argument('action', choices=['read', 'export', 'stats', 'add', 'approve', 'reject'])
    parser.add_argument('-c', '--credentials', required=True, help='Service account JSON')
    parser.add_argument('-u', '--url', required=True, help='Google Sheets URL')
    parser.add_argument('-o', '--output', help='Output file for read/export')
    parser.add_argument('--entity-id', help='Entity ID for add/approve/reject')
    parser.add_argument('--entity-file', help='JSON file with entity data for add')
    parser.add_argument('--notes', help='Notes for approve/reject')
    
    args = parser.parse_args()
    
    sync = EntityLibrarySync(args.credentials, args.url)
    
    if args.action == 'read':
        data = sync.read_library()
        output = json.dumps(data, indent=2)
        if args.output:
            Path(args.output).write_text(output)
        else:
            print(output)
    
    elif args.action == 'export':
        if not args.output:
            print("Error: --output required for export")
            return
        sync.export_to_json(Path(args.output))
        print(f"Exported to {args.output}")
    
    elif args.action == 'stats':
        stats = sync.get_stats()
        print(json.dumps(stats, indent=2))
    
    elif args.action == 'add':
        if not args.entity_file:
            print("Error: --entity-file required for add")
            return
        entity = json.loads(Path(args.entity_file).read_text())
        sync.add_entity(entity)
        print(f"Added entity: {entity.get('entity_id')}")
    
    elif args.action == 'approve':
        if not args.entity_id:
            print("Error: --entity-id required for approve")
            return
        sync.approve_pending(args.entity_id, args.notes or '')
        print(f"Approved: {args.entity_id}")
    
    elif args.action == 'reject':
        if not args.entity_id:
            print("Error: --entity-id required for reject")
            return
        sync.reject_pending(args.entity_id, args.notes or '')
        print(f"Rejected: {args.entity_id}")


if __name__ == '__main__':
    main()
