#!/usr/bin/env python3
"""
Database Administration CLI for Notary Processing Center.
Provides commands for database initialization, backup, querying, and administration.
"""
import argparse
import sys
import json
import gzip
import shutil
from pathlib import Path
from datetime import datetime
from database_manager import DatabaseManager

def cmd_init(args):
    """Initialize database command."""
    db_manager = DatabaseManager(args.database)
    
    # Check if database already exists
    db_path = Path(args.database)
    if db_path.exists() and not args.force:
        print(f"Database already exists at {args.database}")
        print("Use --force to overwrite, or delete the file manually.")
        return 1
    
    # Backup existing if force and exists
    if db_path.exists() and args.force:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = f"{args.database}.backup_{timestamp}"
        print(f"Backing up existing database to {backup_path}")
        if db_manager.backup_database(backup_path):
            print("Backup created successfully")
        else:
            print("Warning: Backup failed")
    
    # Initialize database
    print(f"Initializing database from schema: {args.schema}")
    if not Path(args.schema).exists():
        print(f"Error: Schema file not found: {args.schema}")
        return 1
    
    if db_manager.initialize_database(args.schema):
        print("Database initialized successfully")
        
        # Import existing data if requested
        if args.import_existing:
            from init_database import import_existing_documents
            import_existing_documents(db_manager, args.input_dir, args.ocr_output_dir, args.renamed_dir)
        
        # Show statistics
        stats = db_manager.get_statistics()
        print("\nDatabase Statistics:")
        print(json.dumps(stats, indent=2))
        
        return 0
    else:
        print("Database initialization failed")
        return 1

def cmd_import(args):
    """Import existing documents command."""
    db_manager = DatabaseManager(args.database)
    
    # Check if database exists
    if not Path(args.database).exists():
        print(f"Database does not exist at {args.database}")
        print("Run 'init' command first to create database.")
        return 1
    
    from init_database import import_existing_documents
    imported = import_existing_documents(db_manager, args.input_dir, args.ocr_output_dir, args.renamed_dir)
    
    # Show updated statistics
    stats = db_manager.get_statistics()
    print("\nUpdated Database Statistics:")
    print(json.dumps(stats, indent=2))
    
    return 0

def cmd_stats(args):
    """Show statistics command."""
    db_manager = DatabaseManager(args.database)
    
    # Check if database exists
    if not Path(args.database).exists():
        print(f"Database does not exist at {args.database}")
        return 1
    
    stats = db_manager.get_statistics()
    
    if args.format == 'json':
        print(json.dumps(stats, indent=2))
    else:
        print("=" * 60)
        print("NOTARY PROCESSING CENTER DATABASE STATISTICS")
        print("=" * 60)
        
        print(f"\nDocuments: {stats.get('total_documents', 0)} total")
        for status, count in stats.get('documents_by_status', {}).items():
            print(f"  - {status}: {count}")
        
        print(f"\nProcessing Status:")
        print(f"  - With OCR: {stats.get('documents_with_ocr', 0)}")
        print(f"  - Extracted: {stats.get('documents_extracted', 0)}")
        print(f"  - Renamed: {stats.get('documents_renamed', 0)}")
        
        print(f"\nErrors:")
        print(f"  - Recent unresolved: {stats.get('recent_unresolved_errors', 0)}")
        
        # Show document type statistics if available
        db_manager.connect()
        try:
            db_manager.cursor.execute("SELECT document_type, COUNT(*) as count FROM extracted_data GROUP BY document_type ORDER BY count DESC")
            doc_types = db_manager.cursor.fetchall()
            if doc_types:
                print(f"\nDocument Types:")
                for row in doc_types:
                    print(f"  - {row['document_type'] or 'Unknown'}: {row['count']}")
        except:
            pass  # Table might not exist yet
        finally:
            db_manager.close()
        
        print(f"\nDatabase: {args.database}")
        print(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)
    
    return 0

def cmd_backup(args):
    """Backup database command."""
    db_manager = DatabaseManager(args.database)
    
    # Check if database exists
    if not Path(args.database).exists():
        print(f"Database does not exist at {args.database}")
        return 1
    
    # Determine backup path
    if args.output:
        backup_path = args.output
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = f"{args.database}.backup_{timestamp}"
        if args.compress:
            backup_path += ".gz"
    
    print(f"Creating backup to: {backup_path}")
    
    if args.compress:
        # Create temporary uncompressed backup then compress
        temp_backup = backup_path.replace('.gz', '')
        if db_manager.backup_database(temp_backup):
            try:
                with open(temp_backup, 'rb') as f_in:
                    with gzip.open(backup_path, 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
                Path(temp_backup).unlink()
                print(f"Backup created and compressed: {backup_path}")
                print(f"Size: {Path(backup_path).stat().st_size / 1024 / 1024:.2f} MB")
                return 0
            except Exception as e:
                print(f"Compression failed: {e}")
                # Keep uncompressed backup
                print(f"Uncompressed backup saved at: {temp_backup}")
                return 1
        else:
            return 1
    else:
        if db_manager.backup_database(backup_path):
            print(f"Backup created: {backup_path}")
            print(f"Size: {Path(backup_path).stat().st_size / 1024 / 1024:.2f} MB")
            return 0
        else:
            return 1

def cmd_query(args):
    """Execute custom query command."""
    db_manager = DatabaseManager(args.database)
    
    # Check if database exists
    if not Path(args.database).exists():
        print(f"Database does not exist at {args.database}")
        return 1
    
    # Safety check: prevent destructive queries
    query_lower = args.query.lower().strip()
    destructive_keywords = ['drop', 'delete', 'update', 'insert', 'alter', 'truncate', 'vacuum']
    if any(keyword in query_lower for keyword in destructive_keywords) and not args.allow_write:
        print("Error: Query contains potentially destructive operations.")
        print("Use --allow-write if you intend to modify the database.")
        return 1
    
    try:
        results = db_manager.execute_query(args.query)
        
        if not results:
            print("Query returned no results.")
            return 0
        
        # Display results
        if args.format == 'json':
            print(json.dumps(results, indent=2))
        else:
            # Get column names
            columns = list(results[0].keys())
            
            # Calculate column widths
            col_widths = {}
            for col in columns:
                col_widths[col] = max(len(col), max(len(str(row.get(col, ''))) for row in results))
            
            # Print header
            header = " | ".join(col.ljust(col_widths[col]) for col in columns)
            print(header)
            print("-" * len(header))
            
            # Print rows
            for row in results:
                print(" | ".join(str(row.get(col, '')).ljust(col_widths[col]) for col in columns))
            
            print(f"\nTotal rows: {len(results)}")
        
        return 0
    except Exception as e:
        print(f"Query failed: {e}")
        return 1

def cmd_repair(args):
    """Repair database command."""
    db_manager = DatabaseManager(args.database)
    
    # Check if database exists
    if not Path(args.database).exists():
        print(f"Database does not exist at {args.database}")
        return 1
    
    print(f"Repairing database: {args.database}")
    
    try:
        db_manager.connect()
        
        # Check integrity
        print("Checking database integrity...")
        db_manager.cursor.execute("PRAGMA integrity_check")
        integrity_result = db_manager.cursor.fetchone()
        
        if integrity_result[0] == "ok":
            print("Integrity check passed.")
        else:
            print(f"Integrity issues found: {integrity_result[0]}")
            
            if args.fix:
                print("Attempting to fix issues...")
                # Vacuum to rebuild database
                db_manager.cursor.execute("VACUUM")
                db_manager.conn.commit()
                print("Vacuum completed.")
                
                # Re-check integrity
                db_manager.cursor.execute("PRAGMA integrity_check")
                integrity_result = db_manager.cursor.fetchone()
                if integrity_result[0] == "ok":
                    print("Repair successful.")
                else:
                    print(f"Still have issues: {integrity_result[0]}")
                    print("Consider restoring from backup.")
        
        # Check foreign keys
        print("\nChecking foreign key constraints...")
        db_manager.cursor.execute("PRAGMA foreign_key_check")
        fk_results = db_manager.cursor.fetchall()
        
        if fk_results:
            print(f"Foreign key violations found: {len(fk_results)}")
            for violation in fk_results:
                print(f"  Table: {violation['table']}, Row ID: {violation['rowid']}, Parent: {violation['parent']}")
            
            if args.fix:
                print("Foreign key violations cannot be automatically fixed.")
                print("You may need to manually clean up orphaned records.")
        else:
            print("No foreign key violations found.")
        
        # Backup after repair if requested
        if args.backup_after:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = f"{args.database}.repaired_{timestamp}"
            if db_manager.backup_database(backup_path):
                print(f"\nPost-repair backup created: {backup_path}")
        
        return 0
    except Exception as e:
        print(f"Repair failed: {e}")
        return 1
    finally:
        db_manager.close()

def main():
    parser = argparse.ArgumentParser(
        description="Notary Processing Center Database Administration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s init --force
  %(prog)s stats
  %(prog)s backup --compress
  %(prog)s query "SELECT * FROM documents LIMIT 5"
        """
    )
    
    # Global arguments
    parser.add_argument("--database", default="notary_processing.db",
                       help="Path to SQLite database file (default: notary_processing.db)")
    parser.add_argument("--verbose", "-v", action="store_true",
                       help="Enable verbose logging")
    
    # Subcommands
    subparsers = parser.add_subparsers(dest="command", required=True, help="Command to execute")
    
    # Init command
    init_parser = subparsers.add_parser("init", help="Initialize database")
    init_parser.add_argument("--schema", default="database_schema.sqlite.sql",
                           help="Path to SQL schema file")
    init_parser.add_argument("--force", action="store_true",
                           help="Overwrite existing database without confirmation")
    init_parser.add_argument("--import-existing", action="store_true",
                           help="Import existing processed documents")
    init_parser.add_argument("--input-dir", default="input",
                           help="Input directory with PDF files")
    init_parser.add_argument("--ocr-output-dir", default="ocr-output",
                           help="OCR output directory")
    init_parser.add_argument("--renamed-dir", default="renamed",
                           help="Renamed files directory")
    
    # Import command
    import_parser = subparsers.add_parser("import", help="Import existing documents")
    import_parser.add_argument("--input-dir", default="input",
                             help="Input directory with PDF files")
    import_parser.add_argument("--ocr-output-dir", default="ocr-output",
                             help="OCR output directory")
    import_parser.add_argument("--renamed-dir", default="renamed",
                             help="Renamed files directory")
    
    # Stats command
    stats_parser = subparsers.add_parser("stats", help="Show database statistics")
    stats_parser.add_argument("--format", choices=["text", "json"], default="text",
                            help="Output format")
    
    # Backup command
    backup_parser = subparsers.add_parser("backup", help="Backup database")
    backup_parser.add_argument("--output", help="Custom backup path")
    backup_parser.add_argument("--compress", action="store_true",
                             help="Compress backup with gzip")
    
    # Query command
    query_parser = subparsers.add_parser("query", help="Execute custom SQL query")
    query_parser.add_argument("query", help="SQL query to execute")
    query_parser.add_argument("--format", choices=["text", "json"], default="text",
                            help="Output format")
    query_parser.add_argument("--allow-write", action="store_true",
                            help="Allow write operations (DANGEROUS)")
    
    # Repair command
    repair_parser = subparsers.add_parser("repair", help="Repair database issues")
    repair_parser.add_argument("--fix", action="store_true",
                             help="Attempt to fix issues")
    repair_parser.add_argument("--backup-after", action="store_true",
                             help="Create backup after repair")
    
    args = parser.parse_args()
    
    # Map commands to functions
    commands = {
        'init': cmd_init,
        'import': cmd_import,
        'stats': cmd_stats,
        'backup': cmd_backup,
        'query': cmd_query,
        'repair': cmd_repair
    }
    
    # Execute command
    if args.command in commands:
        return commands[args.command](args)
    else:
        print(f"Unknown command: {args.command}")
        return 1

if __name__ == "__main__":
    sys.exit(main())