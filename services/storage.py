import sqlite3
import json

class Storage:
    def __init__(self):
        self.conn = sqlite3.connect("candidates.db")
        self.create_table()

    def create_table(self):
        with self.conn:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS candidates (
                    id TEXT PRIMARY KEY,
                    metadata TEXT
                )
            """)

    def save_candidate(self, candidate_id: str, metadata: dict):
        with self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO candidates (id, metadata) VALUES (?, ?)",
                (candidate_id, json.dumps(metadata))
            )

    def get_candidate_metadata(self, candidate_id: str) -> dict:
        cursor = self.conn.execute("SELECT metadata FROM candidates WHERE id = ?", (candidate_id,))
        result = cursor.fetchone()
        return json.loads(result[0]) if result else {}