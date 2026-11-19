import sqlite3
from pathlib import Path

DATABASE_NAME = str(Path(__file__).resolve().with_name("specsync.db"))


def get_db_connection():
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def initialize_database():
    conn = get_db_connection()
    conn.execute('''CREATE TABLE IF NOT EXISTS projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, description TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS requirements (
        id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL,
        title TEXT NOT NULL, description TEXT, requirement_type TEXT NOT NULL,
        priority TEXT DEFAULT 'Medium', status TEXT DEFAULT 'Pending', version INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS requirement_versions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, requirement_id INTEGER NOT NULL,
        version_number INTEGER NOT NULL, title TEXT NOT NULL, description TEXT,
        changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(requirement_id) REFERENCES requirements(id) ON DELETE CASCADE,
        UNIQUE(requirement_id, version_number))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS test_cases (
        id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL,
        title TEXT NOT NULL, description TEXT, expected_result TEXT,
        status TEXT DEFAULT 'Not Executed', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS traceability_links (
        id INTEGER PRIMARY KEY AUTOINCREMENT, requirement_id INTEGER NOT NULL,
        test_case_id INTEGER NOT NULL,
        FOREIGN KEY(requirement_id) REFERENCES requirements(id) ON DELETE CASCADE,
        FOREIGN KEY(test_case_id) REFERENCES test_cases(id) ON DELETE CASCADE,
        UNIQUE(requirement_id, test_case_id))''')

    # Safe migrations for existing SQLite databases.
    test_cols = {r["name"] for r in conn.execute("PRAGMA table_info(test_cases)")}
    if "status" not in test_cols:
        conn.execute("ALTER TABLE test_cases ADD COLUMN status TEXT DEFAULT 'Not Executed'")
    req_cols = {r["name"] for r in conn.execute("PRAGMA table_info(requirements)")}
    if "version" not in req_cols:
        conn.execute("ALTER TABLE requirements ADD COLUMN version INTEGER DEFAULT 1")

    conn.execute("UPDATE projects SET name='student management' WHERE LOWER(TRIM(name)) IN ('student mangement','student managment')")
    conn.execute('''INSERT INTO requirement_versions(requirement_id,version_number,title,description)
        SELECT r.id, 1, r.title, r.description FROM requirements r
        WHERE NOT EXISTS (SELECT 1 FROM requirement_versions rv WHERE rv.requirement_id=r.id)''')
    conn.execute("UPDATE test_cases SET status='Not Executed' WHERE status IS NULL OR status NOT IN ('Pass','Fail','Not Executed')")
    conn.commit()
    conn.close()


if __name__ == "__main__":
    initialize_database()
    print("SpecSync database initialized successfully.")
