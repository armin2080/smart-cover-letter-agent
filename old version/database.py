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
    
    EMPLOYMENT_TYPES = ['fulltime', 'parttime', 'workingstudent', 'internship', 'minijob']
    
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
        self.ensure_employment_type_column()

    def ensure_user_id_column(self):
        columns = [row[1] for row in self.fetchall('PRAGMA table_info(jobs)')]
        if 'user_id' not in columns:
            self.execute('ALTER TABLE jobs ADD COLUMN user_id TEXT')

    def ensure_employment_type_column(self):
        columns = [row[1] for row in self.fetchall('PRAGMA table_info(jobs)')]
        if 'employment_type' not in columns:
            self.execute('ALTER TABLE jobs ADD COLUMN employment_type TEXT DEFAULT NULL')

    def add_job(self, title, link, user_id, employment_type=None):
        self.execute(
            'INSERT INTO jobs (title, link, user_id, employment_type) VALUES (?, ?, ?, ?)',
            (title, link, user_id, employment_type)
        )

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
    
    RESUME_FIELDS = [
        'resume_name', 'resume_title', 'resume_phone', 'resume_email',
        'resume_location', 'resume_portfolio', 'resume_skills',
        'resume_education', 'resume_languages', 'resume_experience',
        'resume_projects', 'resume_certs'
    ]

    RESUME_FIELD_LABELS = {
        'resume_name': 'Full Name',
        'resume_title': 'Job Title',
        'resume_phone': 'Phone',
        'resume_email': 'Email',
        'resume_location': 'Location',
        'resume_portfolio': 'Portfolio',
        'resume_skills': 'Skills',
        'resume_education': 'Education',
        'resume_languages': 'Languages',
        'resume_experience': 'Experience',
        'resume_projects': 'Projects',
        'resume_certs': 'Certificates',
        'expected_salary': 'Expected Salary',
        'graduation_date': 'Graduation Date',
    }
    
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
        self.ensure_resume_columns()
        self.ensure_preferred_types_column()

    def ensure_preferred_types_column(self):
        columns = [row[1] for row in self.fetchall('PRAGMA table_info(users)')]
        if 'preferred_types' not in columns:
            self.execute("ALTER TABLE users ADD COLUMN preferred_types TEXT DEFAULT 'fulltime,parttime,workingstudent,internship'")
        if 'chat_id' not in columns:
            self.execute('ALTER TABLE users ADD COLUMN chat_id INTEGER DEFAULT NULL')

    def set_chat_id(self, username, chat_id):
        """Store the user's Telegram chat_id for sending messages."""
        columns = [row[1] for row in self.fetchall('PRAGMA table_info(users)')]
        if 'chat_id' in columns:
            self.execute('UPDATE users SET chat_id = ? WHERE username = ?', (chat_id, username))

    def ensure_resume_columns(self):
        """Add individual resume field columns if they don't exist."""
        columns = [row[1] for row in self.fetchall('PRAGMA table_info(users)')]
        for field in self.RESUME_FIELDS:
            if field not in columns:
                self.execute(f'ALTER TABLE users ADD COLUMN {field} TEXT DEFAULT NULL')

    def add_user(self, name, username, resume=None, expected_salary=None, graduation_date=None):
        self.execute(
            'INSERT INTO users (name, username, resume, expected_salary, graduation_date) VALUES (?, ?, ?, ?, ?)',
            (name, username, resume, expected_salary, graduation_date)
        )

    def get_user(self, username):
        return self.fetchone('SELECT * FROM users WHERE username = ?', (username,))
    
    def update_user(self, username, resume=None, expected_salary=None, graduation_date=None):
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
    
    def save_resume_fields(self, username, resume_fields):
        """Save individual resume fields for a user."""
        updates = []
        params = []
        for field in self.RESUME_FIELDS:
            if field in resume_fields:
                updates.append(f"{field} = ?")
                params.append(resume_fields[field])
        if not updates:
            return
        query = f"UPDATE users SET {', '.join(updates)} WHERE username = ?"
        params.append(username)
        self.execute(query, tuple(params))
    
    def update_resume_field(self, username, field_name, value):
        """Update a single resume field by name."""
        if field_name in self.RESUME_FIELDS or field_name in ('expected_salary', 'graduation_date'):
            self.execute(f'UPDATE users SET {field_name} = ? WHERE username = ?', (value, username))
    
    def get_resume_fields(self, username):
        """Get all individual resume fields as a dict for a user."""
        user = self.get_user(username)
        if not user:
            return None
        # Dynamically map column names to indices using PRAGMA table_info
        columns = [row[1] for row in self.fetchall('PRAGMA table_info(users)')]
        fields = {}
        for field in self.RESUME_FIELDS:
            if field in columns:
                idx = columns.index(field)
                if idx < len(user):
                    fields[field] = user[idx]
                else:
                    fields[field] = None
            else:
                fields[field] = None
        return fields
    
    def get_all_users(self):
        """Get all registered usernames."""
        rows = self.fetchall('SELECT username FROM users')
        return [row[0] for row in rows]
    
    def get_preferred_types(self, username):
        """Get the user's preferred employment types as a list."""
        user = self.get_user(username)
        if not user:
            return ['fulltime', 'parttime', 'workingstudent', 'internship']
        columns = [row[1] for row in self.fetchall('PRAGMA table_info(users)')]
        if 'preferred_types' not in columns:
            return ['fulltime', 'parttime', 'workingstudent', 'internship']
        idx = columns.index('preferred_types')
        raw = user[idx] if idx < len(user) else None
        if not raw:
            return ['fulltime', 'parttime', 'workingstudent', 'internship']
        return [t.strip() for t in raw.split(',') if t.strip()]
    
    def set_preferred_types(self, username, types_list):
        """Set the user's preferred employment types."""
        raw = ','.join(types_list)
        columns = [row[1] for row in self.fetchall('PRAGMA table_info(users)')]
        if 'preferred_types' in columns:
            self.execute('UPDATE users SET preferred_types = ? WHERE username = ?', (raw, username))


if __name__ == "__main__":
    # Database initialization test
    job_db = JobDatabase("test_jobs.db")
    user_db = UserDatabase("test_users.db")
    print("Database tables created successfully.")
    job_db.close()
    user_db.close()
