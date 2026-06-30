import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from app.database import get_db
from app.models import SocialAccount

def main():
    try:
        db = next(get_db())
        accounts = db.query(SocialAccount).all()
        output = []
        output.append(f"Total Accounts: {len(accounts)}")
        for a in accounts:
            output.append(f"ID: {a.id}, Platform: {a.platform}, Display Name: {a.display_name}, Status: {a.status}")
        
        with open("scratch/db_result.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(output))
    except Exception as e:
        with open("scratch/db_result.txt", "w", encoding="utf-8") as f:
            f.write(f"ERROR: {str(e)}")

if __name__ == "__main__":
    main()
