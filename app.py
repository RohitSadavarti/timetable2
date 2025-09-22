# app.py
import streamlit as st
import pandas as pd
import psycopg2
import psycopg2.extras
import random
from datetime import datetime
from collections import defaultdict
import os
from urllib.parse import urlparse

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
    .connection-status {
        padding: 0.5rem;
        border-radius: 5px;
        margin-bottom: 1rem;
        text-align: center;
    }
    .connected {
        background-color: #d4edda;
        color: #155724;
        border: 1px solid #c3e6cb;
    }
    .disconnected {
        background-color: #f8d7da;
        color: #721c24;
        border: 1px solid #f5c6cb;
    }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="main-header">
    <h1>🎓 PostgreSQL Timetable Generator</h1>
    <p>Generate optimal timetables with pre-configured database connection</p>
</div>
""", unsafe_allow_html=True)

# ---------- DB helper class ----------
class PostgresDB:
    def __init__(self):
        self.conn = None
        self.connected = False
    
    def connect(self):
        """Connect using the hardcoded connection details."""
        try:
            self.conn = get_pg_connection()
            self.connected = True
            return True, None
        except Exception as e:
            self.connected = False
            return False, str(e)
    
    def close(self):
        if self.conn:
            try:
                self.conn.close()
            except:
                pass
            self.conn = None
            self.connected = False
    
    def list_tables(self):
        """Return a list of user tables (schema.table)."""
        if not self.conn:
            raise Exception("Not connected")
        cur = self.conn.cursor()
        sql = """
            SELECT table_schema, table_name
            FROM information_schema.tables
            WHERE table_type='BASE TABLE' 
            AND table_schema NOT IN ('pg_catalog', 'information_schema')
            ORDER BY table_schema, table_name;
        """
        cur.execute(sql)
        rows = cur.fetchall()
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
        """Fetch all rows (optionally limited) safely."""
        if not self.conn:
            raise Exception("Not connected")
        
        cur = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        limit_clause = f" LIMIT {limit}" if limit else ""
        sql = f'SELECT * FROM "{schema_name}"."{table_name}"{limit_clause}'
        cur.execute(sql)
        return cur.fetchall()
    
    def query(self, sql, params=None):
        """Run arbitrary SELECT query (read-only)"""
        if not self.conn:
            raise Exception("Not connected")
        cur = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params or ())
        return cur.fetchall()

# ---------- Timetable generator ----------
class SQLTimetableGenerator:
    def __init__(self, db: PostgresDB = None):
        self.db = db or PostgresDB()
        self.timetable = {}
        self.working_days = []
        self.periods_per_day = 6
        self.teacher_workload = defaultdict(int)
        self.class_schedule = defaultdict(lambda: defaultdict(list))
        self.teacher_schedule = defaultdict(lambda: defaultdict(list))
    
    def _find_table(self, candidate_names):
        """Search through DB tables for first match among candidate_names."""
        try:
            all_tables = self.db.list_tables()
            for cand in candidate_names:
                for full in all_tables:
                    if "." in full:
                        sch, tbl = full.split(".", 1)
                    else:
                        sch, tbl = "public", full
                    
                    if (tbl.lower() == cand.lower() or 
                        full.lower() == cand.lower() or 
                        f"{sch}.{tbl}".lower() == cand.lower()):
                        return sch, tbl
            return None, None
        except Exception as e:
            st.error(f"Error finding tables: {e}")
            return None, None
    
    def load_teachers(self):
        sch, tbl = self._find_table(['teachers_table', 'teachers', 'teacher'])
        if not sch:
            raise Exception("No teachers table found (searched: teachers_table, teachers, teacher)")
        
        rows = self.db.fetch_all(sch, tbl)
        if not rows:
            raise Exception("Teachers table is empty")
        
        teachers = {}
        for r in rows:
            teacher_id = (r.get('teacher_id') or r.get('Teacher_ID') or 
                         r.get('id') or r.get('teacherid') or str(len(teachers) + 1))
            teachers[str(teacher_id)] = {
                'name': (r.get('teacher_name') or r.get('Teacher_Name') or 
                        r.get('name') or f"Teacher {teacher_id}"),
                'max_lectures': int(r.get('max_lectures_per_week') or 
                                  r.get('Max_Lectures_Per_Week') or 
                                  r.get('max_lectures') or 20),
                'preferred_slots': (r.get('preferred_slots') or 
                                  r.get('Preferred_Slots') or 'Any')
            }
        return teachers
    
    def load_subjects(self):
        sch, tbl = self._find_table(['subjects_table', 'subjects', 'subject'])
        if not sch:
            raise Exception("No subjects table found (searched: subjects_table, subjects, subject)")
        
        rows = self.db.fetch_all(sch, tbl)
        if not rows:
            raise Exception("Subjects table is empty")
        
        subjects = {}
        for r in rows:
            subject_id = (r.get('subject_id') or r.get('Subject_ID') or 
                         r.get('id') or r.get('subjectid') or str(len(subjects) + 1))
            
            weekly = r.get('weekly_lectures') or r.get('Weekly_Lectures') or r.get('weekly') or 3
            try:
                weekly = int(weekly)
            except:
                weekly = 3
            
            is_common = str(r.get('is_common') or r.get('Is_Common') or '').lower() in ('yes', 'true', '1')
            
            subjects[str(subject_id)] = {
                'name': (r.get('subject_name') or r.get('Subject_Name') or 
                        r.get('name') or f"Subject {subject_id}"),
                'is_common': is_common,
                'weekly_lectures': weekly
            }
        return subjects
    
    def load_classes(self):
        sch, tbl = self._find_table(['classes_table', 'classes', 'class'])
        if not sch:
            raise Exception("No classes table found (searched: classes_table, classes, class)")
        
        rows = self.db.fetch_all(sch, tbl)
        if not rows:
            raise Exception("Classes table is empty")
        
        classes = {}
        for r in rows:
            class_id = (r.get('class_id') or r.get('Class_ID') or 
                       r.get('id') or r.get('classid') or str(len(classes) + 1))
            classes[str(class_id)] = {
                'name': (r.get('class_name') or r.get('Class_Name') or 
                        r.get('name') or str(class_id)),
                'year': r.get('year') or r.get('Year') or 1
            }
        return classes
    
    def load_teacher_subject_mapping(self):
        sch, tbl = self._find_table(['teacher_subject_map_table', 'teacher_subject_map', 'teacher_subject'])
        if not sch:
            raise Exception("No teacher-subject mapping table found")
        
        rows = self.db.fetch_all(sch, tbl)
        if not rows:
            raise Exception("Teacher-subject mapping table is empty")
        
        mappings = []
        for r in rows:
            mappings.append({
                'teacher_id': str(r.get('teacher_id') or r.get('Teacher_ID') or r.get('teacherid')),
                'class_id': str(r.get('class_id') or r.get('Class_ID') or r.get('classid')),
                'subject_id': str(r.get('subject_id') or r.get('Subject_ID') or r.get('subjectid'))
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
                
                if teacher_id in teachers and class_id in classes and subject_id in subjects:
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
    
    def generate_timetable(self, working_days, periods_per_day=6, break_periods=None):
        if break_periods is None:
            break_periods = [4]
        
        self.working_days = working_days
        self.periods_per_day = periods_per_day
        
        assignments, teachers, subjects, classes = self.get_teaching_assignments()
        if not assignments:
            st.error("No teaching assignments found!")
            return False
        
        # Initialize timetable
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
        
        # Reset trackers
        self.teacher_schedule = defaultdict(lambda: defaultdict(list))
        self.class_schedule = defaultdict(lambda: defaultdict(list))
        self.teacher_workload = defaultdict(int)
        
        # Schedule assignments
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
        
        if not workload_data:
            st.info("No workload data to show yet.")
            return
        
        workload_df = pd.DataFrame(workload_data)
        
        def highlight_status(val):
            color = 'lightgreen' if val == 'Optimal' else 'lightcoral'
            return f'background-color: {color}'
        
        styled_df = workload_df.style.applymap(highlight_status, subset=['Status'])
        st.dataframe(styled_df, use_container_width=True)

    def display_timetable(self):
        if not self.timetable:
            st.info("No timetable generated yet.")
            return
        
        st.subheader("📅 Generated Timetables")
        
        for class_id, class_schedule in self.timetable.items():
            with st.expander(f"📚 Class: {class_id}", expanded=True):
                # Create DataFrame for display
                timetable_data = []
                periods = [f'P{i}' for i in range(1, self.periods_per_day + 1)]
                
                for day in self.working_days:
                    row = {'Day': day}
                    for period in periods:
                        entry = class_schedule[day][period]
                        if entry['type'] == 'break':
                            row[period] = f"🍽️ {entry['subject']}"
                        elif entry['type'] == 'free':
                            row[period] = f"🔴 {entry['subject']}"
                        else:
                            row[period] = f"📖 {entry['subject']}\n👨‍🏫 {entry['teacher']}"
                    timetable_data.append(row)
                
                df = pd.DataFrame(timetable_data)
                st.dataframe(df, use_container_width=True)

# ---------- Initialize session state ----------
if 'db' not in st.session_state:
    st.session_state.db = PostgresDB()
if 'generator' not in st.session_state:
    st.session_state.generator = SQLTimetableGenerator(st.session_state.db)
if 'db_connected' not in st.session_state:
    st.session_state.db_connected = False

# ---------- Auto-connect to database ----------
if not st.session_state.db_connected:
    with st.spinner("Connecting to database..."):
        success, error = st.session_state.db.connect()
        if success:
            st.session_state.db_connected = True
        else:
            st.session_state.db_connected = False

# ---------- Connection Status Display ----------
if st.session_state.db_connected:
    st.markdown("""
    <div class="connection-status connected">
        🟢 Connected to PostgreSQL Database
    </div>
    """, unsafe_allow_html=True)
else:
    st.markdown("""
    <div class="connection-status disconnected">
        🔴 Database Connection Failed
    </div>
    """, unsafe_allow_html=True)
    st.error("Failed to connect to the database. Please check your connection settings.")

# ---------- Main Interface ----------
col1, col2 = st.columns([1, 2])

with col1:
    st.subheader("⚙️ Timetable Settings")
    
    # Working Days Selection
    st.write("**Working Days:**")
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
    working_days = []
    
    cols = st.columns(2)
    for i, day in enumerate(days):
        with cols[i % 2]:
            if st.checkbox(day, value=(day != 'Saturday'), key=f"day_{day}"):
                working_days.append(day)
    
    # Periods Configuration
    periods_per_day = st.slider("Periods per Day", 4, 8, 6)
    
    # Break Periods
    break_periods = st.multiselect(
        "Break Periods", 
        options=list(range(1, periods_per_day + 1)), 
        default=[4],
        help="Select which periods should be break/lunch periods"
    )
    
    # Generate Button
    generate_button = st.button("🎯 Generate Timetable", type="primary", use_container_width=True)

with col2:
    # Database Tables Info
    if st.session_state.db_connected:
        if st.button("📊 Show Available Tables"):
            try:
                tables = st.session_state.db.list_tables()
                if tables:
                    st.write("**Available Tables:**")
                    for table in tables:
                        st.write(f"- {table}")
                else:
                    st.info("No user tables found.")
            except Exception as e:
                st.error(f"Error fetching tables: {e}")

# ---------- Generate Timetable ----------
if generate_button:
    if not st.session_state.db_connected:
        st.error("❌ Database connection required.")
    elif not working_days:
        st.error("❌ Please select at least one working day.")
    else:
        with st.spinner("Generating timetable..."):
            success = st.session_state.generator.generate_timetable(
                working_days=working_days,
                periods_per_day=periods_per_day,
                break_periods=break_periods
            )
            
            if success:
                st.session_state.timetable_generated = True

# ---------- Display Results ----------
if getattr(st.session_state, 'timetable_generated', False):
    st.session_state.generator.display_timetable()

# ---------- Footer ----------
st.markdown("---")
st.markdown("*Timetable Generator with PostgreSQL Integration*")
