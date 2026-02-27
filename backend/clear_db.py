"""
Clear Temp Database Script
===========================
This script clears all temporary batch data from the database.
Run this script to reset the batch_uploads and batch_results tables.

Usage:
    python -m backend.clear_db
    
    Or from the backend directory:
    python clear_db.py
"""

import sys
import os
from pathlib import Path

# Add parent directory to path to import database module
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.database import clear_temp_batch_data


def main():
    """Main function to clear temp database"""
    print("\n" + "="*60)
    print("🗑️  CLEARING TEMP DATABASE")
    print("="*60)
    
    try:
        # Ask for confirmation
        response = input("\n⚠️  This will delete all batch upload data. Continue? (yes/no): ")
        
        if response.lower() not in ['yes', 'y']:
            print("\n❌ Operation cancelled by user")
            return
        
        # Clear the database
        clear_temp_batch_data()
        
        print("\n✅ SUCCESS!")
        print("   - batch_uploads table cleared")
        print("   - batch_results table cleared")
        print("   - temp2 table cleared")
        print("   - approval_requests table cleared")
        print("   - Auto-increment counters reset")
        print("\n" + "="*60)
        print("All temporary data cleared! Database ready for new uploads.")
        print("="*60 + "\n")
        
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        print("Failed to clear database\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
