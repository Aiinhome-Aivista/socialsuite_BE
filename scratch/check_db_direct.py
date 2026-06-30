import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from app.database import get_db
from app.models import SocialAccount

def main():
    try:
        db = next(get_db())
        accounts = db.query(SocialAccount).all()
        print("=" * 60)
        print(f"DATABASE CHECK: Found {len(accounts)} connected accounts:")
        print("=" * 60)
        for a in accounts:
            print(f"Account ID: {a.id}")
            print(f"  Platform: {a.platform}")
            print(f"  Display Name: {a.display_name}")
            print(f"  Organization ID: {a.organization_id}")
            print(f"  Status: {a.status}")
            print("-" * 60)
    except Exception as e:
        print(f"ERROR: {str(e)}")

if __name__ == "__main__":
    main()
