import sqlite3

class SQLiteDB:
    """Base class for SQLite database operations."""
    
    def __init__(self, db_path):
        self.db_path = db_path
        self.conn = None

    def connect(self):
        self.conn = sqlite3.connect(self.db_path)

    def execute(self, query, params=None):
        if self.conn is None:
            self.connect()
        cursor = self.conn.cursor()
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        self.conn.commit()
        return cursor

    def fetchall(self, query, params=None):
        cursor = self.execute(query, params)
        return cursor.fetchall()

    def fetchone(self, query, params=None):
        cursor = self.execute(query, params)
        return cursor.fetchone()

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None


class JobDatabase(SQLiteDB):
    """Database for managing job postings and tracking their status."""
    
    def __init__(self, db_path):
        super().__init__(db_path)
        self.create_table()

    def create_table(self):
        self.execute('''
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                link TEXT NOT NULL,
                user_id TEXT NOT NULL,
                checked BOOLEAN DEFAULT 0
            )
        ''')
        self.ensure_user_id_column()

    def ensure_user_id_column(self):
        columns = [row[1] for row in self.fetchall('PRAGMA table_info(jobs)')]
        if 'user_id' not in columns:
            self.execute('ALTER TABLE jobs ADD COLUMN user_id TEXT')

    def add_job(self, title, link, user_id):
        self.execute('INSERT INTO jobs (title, link, user_id) VALUES (?, ?, ?)', (title, link, user_id))

    def get_unchecked_jobs(self, user_id):
        return self.fetchall('SELECT * FROM jobs WHERE checked = 0 AND user_id = ?', (user_id,))

    def mark_job_as_checked(self, job_id, user_id):
        self.execute('UPDATE jobs SET checked = 1 WHERE id = ? AND user_id = ?', (job_id, user_id))

    def get_job_by_id(self, job_id, user_id):
        return self.fetchone('SELECT * FROM jobs WHERE id = ? AND user_id = ?', (job_id, user_id))
    
    def job_exists(self, link, user_id):
        return self.fetchone('SELECT 1 FROM jobs WHERE link = ? AND user_id = ?', (link, user_id)) is not None

    def dedupe_jobs(self, user_id=None):
        """Remove duplicate job rows. If user_id is provided, only dedupe for that user.

        Dedupe key = (normalized_link_without_query, title_lower).
        Returns the number of deleted rows.
        """
        if user_id:
            rows = self.fetchall('SELECT id, link, title FROM jobs WHERE user_id = ?', (user_id,))
        else:
            rows = self.fetchall('SELECT id, link, title FROM jobs')

        seen = {}
        to_delete = []
        for row in rows:
            jid, link, title = row
            norm_link = ''
            if link:
                norm_link = link.split('?')[0].split('#')[0].rstrip('/')
            key = (norm_link, (title or '').strip().lower())
            if key in seen:
                to_delete.append(jid)
            else:
                seen[key] = jid

        for jid in to_delete:
            self.execute('DELETE FROM jobs WHERE id = ?', (jid,))

        return len(to_delete)


class UserDatabase(SQLiteDB):
    """Database for managing user profiles and application preferences."""
    
    def __init__(self, db_path):
        super().__init__(db_path)
        self.create_table()

    def create_table(self):
        self.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                username TEXT NOT NULL,
                resume TEXT DEFAULT NULL,
                expected_salary INTEGER DEFAULT NULL,
                graduation_date TEXT DEFAULT NULL
            )
        ''')

    def add_user(self, name, username, resume=None, expected_salary=None, graduation_date=None):
        self.execute(
            'INSERT INTO users (name, username, resume, expected_salary, graduation_date) VALUES (?, ?, ?, ?, ?)',
            (name, username, resume, expected_salary, graduation_date)
        )

    def get_user(self, username):
        return self.fetchone('SELECT * FROM users WHERE username = ?', (username,))
    
    def update_user(self,username, resume=None, expected_salary=None, graduation_date=None):
        updates = []
        params = []
        if resume:
            updates.append("resume = ?")
            params.append(resume)
        if expected_salary is not None:
            updates.append("expected_salary = ?")
            params.append(expected_salary)
        if graduation_date:
            updates.append("graduation_date = ?")
            params.append(graduation_date)

        if updates:
            query = f"UPDATE users SET {', '.join(updates)} WHERE username = ?"
            params.append(username)
            self.execute(query, tuple(params))


if __name__ == "__main__":
    # Database initialization test
    job_db = JobDatabase("test_jobs.db")
    user_db = UserDatabase("test_users.db")
    print("Database tables created successfully.")
    job_db.close()
    user_db.close()
