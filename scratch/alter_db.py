import sys
import os
import urllib.parse
from sqlalchemy import create_engine, text

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from app.config import settings

def main():
    db_user = settings.DB_USER
    db_password = settings.DB_PASSWORD
    db_host = settings.DB_HOST
    db_port = settings.DB_PORT
    db_name = settings.DB_NAME

    pwd = urllib.parse.quote_plus(db_password)
    db_url = f"mysql+pymysql://{db_user}:{pwd}@{db_host}:{db_port}/{db_name}"

    print(f"Connecting to database: {db_name} on {db_host}...")
    try:
        engine = create_engine(db_url)
        with engine.begin() as connection:
            print("Altering 'social_accounts' table...")
            connection.execute(text(
                "ALTER TABLE social_accounts MODIFY COLUMN platform "
                "ENUM('facebook', 'instagram', 'linkedin', 'x', 'youtube', 'pinterest', 'google_analytics') NOT NULL;"
            ))
            
            print("Altering 'post_targets' table...")
            connection.execute(text(
                "ALTER TABLE post_targets MODIFY COLUMN platform "
                "ENUM('facebook', 'instagram', 'linkedin', 'x', 'youtube', 'pinterest', 'google_analytics') NOT NULL;"
            ))
            
            print("\nDatabase columns altered successfully!")
    except Exception as e:
        print(f"\nERROR Altering Database: {e}")

if __name__ == "__main__":
    main()
