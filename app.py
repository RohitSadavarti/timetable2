# app.py
import streamlit as st
import pandas as pd
import mysql.connector
import psycopg2
import psycopg2.extras
import random
from datetime import datetime
from collections import defaultdict
import os
from urllib.parse import urlparse

CORS(app)

# Database configuration
app.config['UPLOAD_FOLDER'] = 'uploads/'
app.config['ALLOWED_EXTENSIONS'] = {'xlsx', 'xls', 'csv'}
app.config['PG_HOST'] = 'aws-0-ap-south-1.pooler.supabase.com'
app.config['PG_USER'] = 'postgres.avqpzwgdylnklbkyqukp'  # change to your PostgreSQL username
app.config['PG_PASSWORD'] = 'asBjLmDfKfoZPVt9'  # change to your PostgreSQL password
app.config['PG_DB'] = 'postgres'  # change to your PostgreSQL database name
app.config['sslmode']='require'

def get_pg_connection():
    return psycopg2.connect(
        host="aws-0-ap-south-1.pooler.supabase.com",
        database="postgres",
        user="postgres.avqpzwgdylnklbkyqukp",
        password="asBjLmDfKfoZPVt9",
        port=6543,
        sslmode='require'
    )


# ---------- Page config & CSS ----------
st.set_page_config(
    page_title="Postgres Timetable Generator",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .main-header {
        background: linear-gradient(90deg, #4CAF50, #2196F3);
        padding: 1rem;
        border-radius: 10px;
        color: white;
        text-align: center;
        margin-bottom: 2rem;
    }
    .success-cell {
        background-color: #e8f5e8 !important;
        color: #2e7d32;
        font-weight: bold;
    }
    .break-cell {
        background-color: #fff3e0 !important;
        color: #ff6f00;
        font-weight: bold;
    }
    .conflict-cell {
        background-color: #ffebee !important;
        color: #d32f2f;
        font-weight: bold;
    }
    .free-cell {
        background-color: #f5f5f5 !important;
        color: #666;
    }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="main-header">
    <h1>🎓 PostgreSQL Timetable Generator</h1>
    <p>Connect to your PostgreSQL database and generate optimal timetables</p>
</div>
""", unsafe_allow_html=True)

# ---------- DB helper class ----------
class PostgresDB:
    def __init__(self):
        self.conn = None
        self.dsn = None
        self.schema = None  # optional schema to search
    
    def connect(self, *, database_url=None, host=None, port=None, dbname=None, user=None, password=None, schema=None):
        """
        Connect using a full DATABASE_URL or individual components.
        DATABASE_URL example: postgresql://user:password@host:5432/dbname
        """
        try:
            if database_url:
                # parse and use as dsn for psycopg2
                self.dsn = database_url
                self.conn = psycopg2.connect(self.dsn)
            else:
                host = host or "localhost"
                port = port or 5432
                dbname = dbname or "postgres"
                self.conn = psycopg2.connect(host=host, port=port, dbname=dbname, user=user, password=password)
                # construct dsn string for informational use
                self.dsn = f"postgresql://{user or ''}:****@{host}:{port}/{dbname}"
            self.schema = schema  # optional schema name to use when querying metadata
            return True, None
        except Exception as e:
            return False, str(e)
    
    def close(self):
        if self.conn:
            try:
                self.conn.close()
            except:
                pass
            self.conn = None
    
    def list_tables(self):
        """Return a list of user tables (schema.table)."""
        if not self.conn:
            raise Exception("Not connected")
        cur = self.conn.cursor()
        schema_filter = f"AND table_schema = '{self.schema}'" if self.schema else "AND table_schema NOT IN ('pg_catalog', 'information_schema')"
        sql = f"""
            SELECT table_schema, table_name
            FROM information_schema.tables
            WHERE table_type='BASE TABLE' {schema_filter}
            ORDER BY table_schema, table_name;
        """
        cur.execute(sql)
        rows = cur.fetchall()
        # return list of "schema.table" or just table if schema is default
        return [f"{r[0]}.{r[1]}" for r in rows]
    
    def get_table_columns(self, schema_name, table_name):
        """Return list of columns for given schema and table."""
        if not self.conn:
            raise Exception("Not connected")
        cur = self.conn.cursor()
        sql = """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            ORDER BY ordinal_position;
        """
        cur.execute(sql, (schema_name, table_name))
        return [r[0] for r in cur.fetchall()]
    
    def fetch_all(self, schema_name, table_name, limit=None):
        """Fetch all rows (optionally limited) safely by validating schema and table names."""
        if not self.conn:
            raise Exception("Not connected")
        # Safe guard: only use allowed identifiers obtained from list_tables
        qualified = f"{schema_name}.{table_name}"
        allowed = set(self.list_tables())
        if qualified not in allowed:
            raise Exception(f"Table {qualified} not found or not allowed")
        
        cur = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        if limit:
            cur.execute(f"SELECT * FROM {psycopg2.sql.Identifier(schema_name).string}.{psycopg2.sql.Identifier(table_name).string} LIMIT %s")
        # Using formatted SQL above with identifiers is tricky; instead use safe string with placeholders after validation:
        cur.execute(f"SELECT * FROM \"{schema_name}\".\"{table_name}\"" + (f" LIMIT %s" if limit else ""), (limit,) if limit else None)
        return cur.fetchall()
    
    def query(self, sql, params=None):
        """Run arbitrary SELECT query (read-only)"""
        if not self.conn:
            raise Exception("Not connected")
        cur = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params or ())
        return cur.fetchall()

# ---------- Timetable generator (logic ported from your version) ----------
class SQLTimetableGenerator:
    def __init__(self, db: PostgresDB = None):
        self.db = db or PostgresDB()
        self.timetable = {}
        self.working_days = []
        self.periods_per_day = 6
        self.teacher_workload = defaultdict(int)
        self.class_schedule = defaultdict(lambda: defaultdict(list))
        self.teacher_schedule = defaultdict(lambda: defaultdict(list))
    
    # ---- Database dependent loaders ----
    def _find_table(self, candidate_names):
        """Search through DB tables for first match among candidate_names.
           Returns (schema, table) or (None, None)"""
        all_tables = self.db.list_tables()
        # all_tables entries look like 'schema.table'
        for cand in candidate_names:
            for full in all_tables:
                sch, tbl = full.split(".", 1)
                if tbl.lower() == cand.lower() or full.lower() == cand.lower() or f"{sch}.{tbl}".lower() == cand.lower():
                    return sch, tbl
        return None, None
    
    def load_teachers(self):
        cur = self.db
        sch, tbl = self._find_table(['Teachers_Table', 'Teachers', 'Teacher', 'teachers'])
        if not sch:
            raise Exception("No teachers table found (searched Teachers / Teacher / teachers)")
        rows = cur.fetch_all(sch, tbl, limit=None)
        if not rows:
            raise Exception("Teachers table is empty")
        
        # Normalize columns
        teachers = {}
        for r in rows:
            # r is a dict (RealDictCursor)
            teacher_id = r.get('Teacher_ID') or r.get('teacher_id') or r.get('id') or r.get('teacherid')
            if teacher_id is None:
                # fallback: use row number
                teacher_id = str(len(teachers) + 1)
            teachers[teacher_id] = {
                'name': r.get('Teacher_Name') or r.get('teacher_name') or r.get('name') or f"Teacher {teacher_id}",
                'max_lectures': int(r.get('Max_Lectures_Per_Week') or r.get('max_lectures_per_week') or r.get('max_lectures') or 20),
                'preferred_slots': r.get('Preferred_Slots') or r.get('preferred_slots') or 'Any'
            }
        return teachers
    
    def load_subjects(self):
        cur = self.db
        sch, tbl = self._find_table(['Subjects_Table', 'Subjects', 'Subject', 'subjects'])
        if not sch:
            raise Exception("No subjects table found (searched Subjects / Subject / subjects)")
        rows = cur.fetch_all(sch, tbl, limit=None)
        if not rows:
            raise Exception("Subjects table is empty")
        subjects = {}
        for r in rows:
            subject_id = r.get('Subject_ID') or r.get('subject_id') or r.get('id') or r.get('subjectid')
            if subject_id is None:
                subject_id = str(len(subjects) + 1)
            weekly = r.get('Weekly_Lectures') or r.get('weekly_lectures') or r.get('weekly') or 3
            # ensure numeric
            try:
                weekly = int(weekly)
            except:
                weekly = 3
            is_common = (r.get('Is_Common') or r.get('is_common') or '').lower() in ('yes', 'true', '1')
            subjects[subject_id] = {
                'name': r.get('Subject_Name') or r.get('subject_name') or r.get('name') or f"Subject {subject_id}",
                'is_common': is_common,
                'weekly_lectures': weekly
            }
        return subjects
    
    def load_classes(self):
        cur = self.db
        sch, tbl = self._find_table(['Classes_Table', 'Classes', 'Class', 'classes'])
        if not sch:
            raise Exception("No classes table found (searched Classes / Class / classes)")
        rows = cur.fetch_all(sch, tbl, limit=None)
        if not rows:
            raise Exception("Classes table is empty")
        classes = {}
        for r in rows:
            class_id = r.get('Class_ID') or r.get('class_id') or r.get('id') or r.get('classid')
            if class_id is None:
                class_id = str(len(classes) + 1)
            classes[class_id] = {
                'name': r.get('Class_Name') or r.get('class_name') or r.get('name') or class_id,
                'year': r.get('Year') or r.get('year') or 1
            }
        return classes
    
    def load_teacher_subject_mapping(self):
        cur = self.db
        sch, tbl = self._find_table(['Teacher_Subject_Map_Table', 'Teacher_Subject_Map', 'teacher_subject_map', 'teacher_subject'])
        if not sch:
            raise Exception("No teacher-subject mapping table found (searched Teacher_Subject_Map / teacher_subject_map)")
        rows = cur.fetch_all(sch, tbl, limit=None)
        if not rows:
            raise Exception("Teacher-subject mapping table is empty")
        mappings = []
        for r in rows:
            mappings.append({
                'teacher_id': r.get('Teacher_ID') or r.get('teacher_id') or r.get('teacherid'),
                'class_id': r.get('Class_ID') or r.get('class_id') or r.get('classid'),
                'subject_id': r.get('Subject_ID') or r.get('subject_id') or r.get('subjectid')
            })
        return mappings
    
    def get_teaching_assignments(self):
        try:
            teachers = self.load_teachers()
            subjects = self.load_subjects()
            classes = self.load_classes()
            mappings = self.load_teacher_subject_mapping()
            
            assignments = []
            for mapping in mappings:
                teacher_id = mapping['teacher_id']
                class_id = mapping['class_id']
                subject_id = mapping['subject_id']
                
                if teacher_id in teachers_table and class_id in classes and subject_id in subjects:
                    weekly_lectures = subjects[subject_id]['weekly_lectures']
                    for lecture_num in range(weekly_lectures):
                        assignments.append({
                            'teacher_id': teacher_id,
                            'teacher_name': teachers[teacher_id]['name'],
                            'class_id': class_id,
                            'class_name': classes[class_id]['name'],
                            'subject_id': subject_id,
                            'subject_name': subjects[subject_id]['name'],
                            'lecture_number': lecture_num + 1,
                            'weekly_lectures': weekly_lectures
                        })
            return assignments, teachers, subjects, classes
        except Exception as e:
            st.error(f"Error loading data: {e}")
            return [], {}, {}, {}
    
    # ---- Timetable logic ----
    def generate_timetable(self, working_days, periods_per_day=6, break_periods=None):
        if break_periods is None:
            break_periods = [4]
        self.working_days = working_days
        self.periods_per_day = periods_per_day
        
        assignments, teachers, subjects, classes = self.get_teaching_assignments()
        if not assignments:
            st.error("No teaching assignments found!")
            return False
        
        # initialize
        self.timetable = {}
        for class_id in classes:
            self.timetable[class_id] = {}
            for day in working_days:
                self.timetable[class_id][day] = {}
                for period in range(1, periods_per_day + 1):
                    if period in break_periods:
                        self.timetable[class_id][day][f'P{period}'] = {
                            'type': 'break',
                            'subject': 'Lunch Break',
                            'teacher': '---',
                            'subject_id': None,
                            'teacher_id': None
                        }
                    else:
                        self.timetable[class_id][day][f'P{period}'] = {
                            'type': 'free',
                            'subject': 'Free Period',
                            'teacher': '---',
                            'subject_id': None,
                            'teacher_id': None
                        }
        # reset trackers
        self.teacher_schedule = defaultdict(lambda: defaultdict(list))
        self.class_schedule = defaultdict(lambda: defaultdict(list))
        self.teacher_workload = defaultdict(int)
        
        random.shuffle(assignments)
        scheduled = 0
        total = len(assignments)
        for assignment in assignments:
            if self.schedule_assignment(assignment, teachers, break_periods):
                scheduled += 1
        
        if scheduled == total:
            st.success(f"✅ Successfully scheduled all {scheduled} lectures!")
        else:
            st.warning(f"⚠️ Scheduled {scheduled} out of {total} lectures. {total - scheduled} conflicts remain.")
        
        self.check_teacher_workload(teachers)
        return True
    
    def schedule_assignment(self, assignment, teachers, break_periods):
        teacher_id = assignment['teacher_id']
        class_id = assignment['class_id']
        max_lectures = teachers[teacher_id]['max_lectures']
        if self.teacher_workload[teacher_id] >= max_lectures:
            return False
        available_slots = []
        for day in self.working_days:
            for period in range(1, self.periods_per_day + 1):
                if period in break_periods:
                    continue
                period_key = f'P{period}'
                if (period_key not in self.teacher_schedule[teacher_id][day] and
                    period_key not in self.class_schedule[class_id][day] and
                    self.timetable[class_id][day][period_key]['type'] == 'free'):
                    available_slots.append((day, period_key))
        if not available_slots:
            return False
        day, period_key = random.choice(available_slots)
        self.timetable[class_id][day][period_key] = {
            'type': 'lecture',
            'subject': assignment['subject_name'],
            'teacher': assignment['teacher_name'],
            'subject_id': assignment['subject_id'],
            'teacher_id': assignment['teacher_id']
        }
        self.teacher_schedule[teacher_id][day].append(period_key)
        self.class_schedule[class_id][day].append(period_key)
        self.teacher_workload[teacher_id] += 1
        return True
    
    def check_teacher_workload(self, teachers):
        st.subheader("👨‍🏫 Teacher Workload Analysis")
        workload_data = []
        for teacher_id, current_load in self.teacher_workload.items():
            max_load = teachers[teacher_id]['max_lectures']
            teacher_name = teachers[teacher_id]['name']
            utilization = round((current_load / max_load) * 100, 1) if max_load > 0 else 0
            workload_data.append({
                'Teacher ID': teacher_id,
                'Teacher Name': teacher_name,
                'Current Load': current_load,
                'Max Load': max_load,
                'Utilization (%)': utilization,
                'Status': 'Optimal' if current_load <= max_load else 'Overloaded'
            })
        workload_df = pd.DataFrame(workload_data)
        if workload_df.empty:
            st.info("No workload data to show yet.")
            return
        def highlight_status(val):
            color = 'lightgreen' if val == 'Optimal' else 'lightcoral'
            return f'background-color: {color}'
        styled_df = workload_df.style.applymap(highlight_status, subset=['Status'])
        st.dataframe(styled_df, use_container_width=True)

# ---------- Initialize session state ----------
if 'db' not in st.session_state:
    st.session_state.db = PostgresDB()
if 'generator' not in st.session_state:
    st.session_state.generator = SQLTimetableGenerator(st.session_state.db)

# ---------- Sidebar: DB connection UI ----------
with st.sidebar:
    st.header("🔧 Database Configuration (Postgres)")
    st.write("Connect using a DATABASE URL or provide components.")
    use_url = st.checkbox("Use DATABASE_URL (single string)", value=True)
    
    if use_url:
        database_url = st.text_input("DATABASE_URL", placeholder="postgresql://user:pass@host:port/dbname")
    else:
        host = st.text_input("Host", value="localhost")
        port = st.text_input("Port", value="5432")
        dbname = st.text_input("DB name", value="postgres")
        user = st.text_input("User", value="")
        password = st.text_input("Password", type="password")
    schema_input = st.text_input("Optional schema to search (leave blank to use public/default)", value="")
    
    if st.button("🔗 Connect to PostgreSQL"):
        try:
            if use_url:
                ok, err = st.session_state.db.connect(database_url=database_url, schema=schema_input or None)
            else:
                ok, err = st.session_state.db.connect(host=host, port=int(port), dbname=dbname, user=user, password=password, schema=schema_input or None)
            if ok:
                st.success("Connected to PostgreSQL!")
                st.session_state.db_connected = True
            else:
                st.error(f"Failed to connect: {err}")
                st.session_state.db_connected = False
        except Exception as e:
            st.error(f"Error: {e}")
            st.session_state.db_connected = False
    
    if st.button("📊 Show DB Tables") and getattr(st.session_state, 'db_connected', False):
        try:
            tables = st.session_state.db.list_tables()
            if tables:
                st.write("Found tables:")
                st.write(tables)
            else:
                st.info("No user tables found.")
        except Exception as e:
            st.error(str(e))
    
    st.divider()
    st.subheader("Timetable Settings")
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
    working_days = []
    cols = st.columns(2)
    for i, day in enumerate(days):
        with cols[i % 2]:
            if st.checkbox(day, value=(day != 'Saturday')):
                working_days.append(day)
    periods_per_day = st.slider("Periods per Day", 4, 8, 6)
    break_periods = st.multiselect("Break Periods", options=list(range(1, periods_per_day + 1)), default=[4])
    
    if st.button("🎯 Generate Timetable"):
        if not getattr(st.session_state, 'db_connected', False):
            st.error("❌ Connect to the database first.")
        elif not working_days:
            st.error("❌ Select at least one working day.")
       
