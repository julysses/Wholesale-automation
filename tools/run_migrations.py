"""
Automated Database Migration Runner.
Reads SQL files from frontend/supabase/migrations/ and executes them in order.
"""

import os
import re
from pathlib import Path
import sqlalchemy
from sqlalchemy import create_engine, text

def run_migrations():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        # Try to build from Supabase vars if available
        sb_url = os.getenv("SUPABASE_URL")
        if not sb_url:
            print("Error: DATABASE_URL or SUPABASE_URL not set.")
            return

    print(f"Connecting to database...")
    engine = create_engine(db_url)
    
    migrations_dir = Path("frontend/supabase/migrations")
    if not migrations_dir.exists():
        print(f"Error: Migrations directory {migrations_dir} not found.")
        return

    # 1. Create migrations table if not exists
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS _migrations (
                id SERIAL PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                executed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
        """))

    # 2. Get executed migrations
    with engine.connect() as conn:
        result = conn.execute(text("SELECT name FROM _migrations"))
        executed_migrations = {row[0] for row in result}

    # 3. Find and sort migration files
    migration_files = sorted(migrations_dir.glob("*.sql"))
    
    for mg_file in migration_files:
        if mg_file.name in executed_migrations:
            print(f"Skipping {mg_file.name} (already executed)")
            continue
        
        print(f"Executing {mg_file.name}...")
        sql = mg_file.read_text()
        
        # Split by ';' but be careful with functions/triggers
        # For simplicity and reliability, we'll try to execute the whole file
        # If it contains multiple statements that SQLAlchemy can't handle at once,
        # we might need to split. But PostgreSQL handles multiple statements in one call.
        
        try:
            with engine.begin() as conn:
                # Some migrations might have multiple statements
                # We use raw connection for better support of multi-statement SQL if needed,
                # but engine.begin() + text() usually works for Postgres.
                conn.execute(text(sql))
                conn.execute(text("INSERT INTO _migrations (name) VALUES (:name)"), {"name": mg_file.name})
            print(f"Successfully executed {mg_file.name}")
        except Exception as e:
            print(f"Error executing {mg_file.name}: {e}")
            # If a migration fails, we stop to prevent further issues
            break

if __name__ == "__main__":
    run_migrations()
