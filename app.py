import streamlit as st
import pandas as pd
import psycopg2
import random
from datetime import datetime, timedelta
import numpy as np
from collections import defaultdict
import os
from urllib.parse import urlparse

# Page configuration
st.set_page_config(
    page_title="PostgreSQL Timetable Generator",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better styling
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
    .metric-card {
        background-color: #f8f9fa;
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid #4CAF50;
        margin: 0.5rem 0;
    }
</style>
""", unsafe_allow_html=True)

# Title
st.markdown("""
<div class="main-header">
    <h1>🎓 PostgreSQL Timetable Generator</h1>
    <p>Connect to PostgreSQL database and generate optimal timetables</p>
</div>
""", unsafe_allow_html=True)

class PostgreSQLTimetableGenerator:
    def __init__(self):
        self.conn = None
        self.timetable = {}
        self.working_days = []
        self.periods_per_day = 6
        self.teacher_workload = defaultdict(int)
        self.class_schedule = defaultdict(lambda: defaultdict(list))
        self.teacher_schedule = defaultdict(lambda: defaultdict(list))
        
    def connect_to_database(self, connection_params=None, database_url=None):
        """Connect to PostgreSQL database"""
        try:
            if database_url:
                # Parse database URL (for Render/Heroku style)
                self.conn = psycopg2.connect(database_url)
            elif connection_params:
                # Connect using individual parameters
                self.conn = psycopg2.connect(
                    host=connection_params['host'],
                    port=connection_params['port'],
                    database=connection_params['database'],
                    user=connection_params['user'],
                    password=connection_params['password']
                )
            else:
                raise Exception("No connection parameters provided")
            
            # Test connection
            cursor = self.conn.cursor()
            cursor.execute("SELECT version();")
            version = cursor.fetchone()
            
            # Get table list
            cursor.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
            """)
            tables = cursor.fetchall()
            
            st.success(f"✅ Connected to PostgreSQL! Found {len(tables)} tables.")
            return True
            
        except Exception as e:
            st.error(f"❌ Failed to connect to PostgreSQL: {e}")
            return False
    
    def get_database_info(self):
        """Get information about database tables and structure"""
        if not self.conn:
            return None
            
        cursor = self.conn.cursor()
        
        try:
            # Get all tables
            cursor.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
                ORDER BY table_name
            """)
            tables = [row[0] for row in cursor.fetchall()]
            
            info = {"tables": {}}
            
            for table in tables:
                # Get column information
                cursor.execute("""
                    SELECT column_name, data_type 
                    FROM information_schema.columns 
                    WHERE table_name = %s AND table_schema = 'public'
                    ORDER BY ordinal_position
                """, (table,))
                columns = cursor.fetchall()
                
                # Get row count
                cursor.execute(f'SELECT COUNT(*) FROM "{table}"')
                count = cursor.fetchone()[0]
                
                info["tables"][table] = {
                    "columns": [f"{col[0]} ({col[1]})" for col in columns],
                    "row_count": count
                }
            
            return info
            
        except Exception as e:
            st.error(f"Error getting database info: {e}")
            return None
    
    def load_teachers(self):
        """Load teachers from database"""
        cursor = self.conn.cursor()
        
        # Try different possible table names (case-insensitive)
        possible_tables = ['teachers_table', 'Teachers_Table', 'teachers', 'Teachers', 'teacher', 'Teacher']
        teachers_data = []
        columns = []
        
        for table_name in possible_tables:
            try:
                cursor.execute(f'SELECT * FROM "{table_name}"')
                teachers_data = cursor.fetchall()
                
                # Get column names
                cursor.execute("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = %s AND table_schema = 'public'
                    ORDER BY ordinal_position
                """, (table_name.lower(),))
                columns = [col[0] for col in cursor.fetchall()]
                break
            except:
                continue
        
        if not teachers_data:
            raise Exception("No teachers table found")
            
        teachers = {}
        for row in teachers_data:
            row_dict = dict(zip(columns, row))
            
            # Handle different column naming conventions
            teacher_id = (row_dict.get('teacher_id') or 
                         row_dict.get('Teacher_ID') or 
                         row_dict.get('teacherId'))
            
            teachers[teacher_id] = {
                'name': (row_dict.get('teacher_name') or 
                        row_dict.get('Teacher_Name') or 
                        row_dict.get('name') or 
                        f'Teacher {teacher_id}'),
                'max_lectures': (row_dict.get('max_lectures_per_week') or 
                               row_dict.get('Max_Lectures_Per_Week') or 
                               row_dict.get('max_lectures') or 20),
                'preferred_slots': (row_dict.get('preferred_slots') or 
                                  row_dict.get('Preferred_Slots') or 'Any')
            }
        
        return teachers
    
    def load_subjects(self):
        """Load subjects from database"""
        cursor = self.conn.cursor()
        
        possible_tables = ['subjects_table', 'Subjects_Table', 'subjects', 'Subjects', 'subject', 'Subject']
        subjects_data = []
        columns = []
        
        for table_name in possible_tables:
            try:
                cursor.execute(f'SELECT * FROM "{table_name}"')
                subjects_data = cursor.fetchall()
                
                cursor.execute("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = %s AND table_schema = 'public'
                    ORDER BY ordinal_position
                """, (table_name.lower(),))
                columns = [col[0] for col in cursor.fetchall()]
                break
            except:
                continue
        
        if not subjects_data:
            raise Exception("No subjects table found")
            
        subjects = {}
        for row in subjects_data:
            row_dict = dict(zip(columns, row))
            
            subject_id = (row_dict.get('subject_id') or 
                         row_dict.get('Subject_ID') or 
                         row_dict.get('subjectId'))
            
            subjects[subject_id] = {
                'name': (row_dict.get('subject_name') or 
                        row_dict.get('Subject_Name') or 
                        row_dict.get('name') or 
                        f'Subject {subject_id}'),
                'is_common': (row_dict.get('is_common') or 
                            row_dict.get('Is_Common') == 'Yes'),
                'weekly_lectures': (row_dict.get('weekly_lectures') or 
                                  row_dict.get('Weekly_Lectures') or 3)
            }
        
        return subjects
    
    def load_classes(self):
        """Load classes from database"""
        cursor = self.conn.cursor()
        
        possible_tables = ['classes_table', 'Classes_Table', 'classes', 'Classes', 'class', 'Class']
        classes_data = []
        columns = []
        
        for table_name in possible_tables:
            try:
                cursor.execute(f'SELECT * FROM "{table_name}"')
                classes_data = cursor.fetchall()
                
                cursor.execute("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = %s AND table_schema = 'public'
                    ORDER BY ordinal_position
                """, (table_name.lower(),))
                columns = [col[0] for col in cursor.fetchall()]
                break
            except:
                continue
        
        if not classes_data:
            raise Exception("No classes table found")
            
        classes = {}
        for row in classes_data:
            row_dict = dict(zip(columns, row))
            
            class_id = (row_dict.get('class_id') or 
                       row_dict.get('Class_ID') or 
                       row_dict.get('classId'))
            
            classes[class_id] = {
                'name': (row_dict.get('class_name') or 
                        row_dict.get('Class_Name') or 
                        row_dict.get('name') or 
                        class_id),
                'year': (row_dict.get('year') or 
                        row_dict.get('Year') or 1)
            }
        
        return classes
    
    def load_teacher_subject_mapping(self):
        """Load teacher-subject-class mappings"""
        cursor = self.conn.cursor()
        
        possible_tables = [
            'teacher_subject_map_table', 'Teacher_Subject_Map_Table',
            'teacher_subject_map', 'Teacher_Subject_Map',
            'mapping', 'Mapping'
        ]
        mapping_data = []
        columns = []
        
        for table_name in possible_tables:
            try:
                cursor.execute(f'SELECT * FROM "{table_name}"')
                mapping_data = cursor.fetchall()
                
                cursor.execute("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = %s AND table_schema = 'public'
                    ORDER BY ordinal_position
                """, (table_name.lower(),))
                columns = [col[0] for col in cursor.fetchall()]
                break
            except:
                continue
        
        if not mapping_data:
            raise Exception("No teacher-subject mapping table found")
        
        mappings = []
        for row in mapping_data:
            row_dict = dict(zip(columns, row))
            mappings.append({
                'teacher_id': (row_dict.get('teacher_id') or 
                              row_dict.get('Teacher_ID')),
                'class_id': (row_dict.get('class_id') or 
                            row_dict.get('Class_ID')),
                'subject_id': (row_dict.get('subject_id') or 
                              row_dict.get('Subject_ID'))
            })
        
        return mappings
    
    def get_teaching_assignments(self):
        """Get complete teaching assignments with subject details"""
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
                    # Create multiple assignments based on weekly lectures
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
        """Generate timetable using constraint satisfaction"""
        if break_periods is None:
            break_periods = [4]  # Lunch break at period 4
            
        self.working_days = working_days
        self.periods_per_day = periods_per_day
        
        # Get all teaching assignments
        assignments, teachers, subjects, classes = self.get_teaching_assignments()
        
        if not assignments:
            st.error("No teaching assignments found!")
            return False
        
        # Initialize timetable structure
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
        
        # Reset tracking variables
        self.teacher_schedule = defaultdict(lambda: defaultdict(list))
        self.class_schedule = defaultdict(lambda: defaultdict(list))
        self.teacher_workload = defaultdict(int)
        
        # Shuffle assignments for randomization
        random.shuffle(assignments)
        
        # Schedule assignments using constraint satisfaction
        scheduled = 0
        total = len(assignments)
        
        for assignment in assignments:
            if self.schedule_assignment(assignment, teachers, break_periods):
                scheduled += 1
        
        # Report results
        success_rate = (scheduled / total) * 100 if total > 0 else 0
        
        if success_rate == 100:
            st.success(f"✅ Perfect! Scheduled all {scheduled} lectures successfully!")
        elif success_rate >= 90:
            st.success(f"✅ Excellent! Scheduled {scheduled}/{total} lectures ({success_rate:.1f}%)")
        elif success_rate >= 70:
            st.warning(f"⚠️ Good! Scheduled {scheduled}/{total} lectures ({success_rate:.1f}%)")
        else:
            st.error(f"❌ Only scheduled {scheduled}/{total} lectures ({success_rate:.1f}%)")
        
        # Check teacher workload
        self.check_teacher_workload(teachers)
        
        return True
    
    def schedule_assignment(self, assignment, teachers, break_periods):
        """Try to schedule a single assignment"""
        teacher_id = assignment['teacher_id']
        class_id = assignment['class_id']
        
        # Get teacher's maximum lectures per week
        max_lectures = teachers[teacher_id]['max_lectures']
        
        # Check if teacher has exceeded workload
        if self.teacher_workload[teacher_id] >= max_lectures:
            return False
        
        # Try to find a suitable slot
        available_slots = []
        
        for day in self.working_days:
            for period in range(1, self.periods_per_day + 1):
                if period in break_periods:
                    continue
                    
                period_key = f'P{period}'
                
                # Check if slot is available for both teacher and class
                if (period_key not in self.teacher_schedule[teacher_id][day] and
                    period_key not in self.class_schedule[class_id][day] and
                    self.timetable[class_id][day][period_key]['type'] == 'free'):
                    
                    available_slots.append((day, period_key))
        
        # If no slots available, return False
        if not available_slots:
            return False
        
        # Choose a random available slot
        day, period_key = random.choice(available_slots)
        
        # Schedule the assignment
        self.timetable[class_id][day][period_key] = {
            'type': 'lecture',
            'subject': assignment['subject_name'],
            'teacher': assignment['teacher_name'],
            'subject_id': assignment['subject_id'],
            'teacher_id': assignment['teacher_id']
        }
        
        # Update tracking
        self.teacher_schedule[teacher_id][day].append(period_key)
        self.class_schedule[class_id][day].append(period_key)
        self.teacher_workload[teacher_id] += 1
        
        return True
    
    def check_teacher_workload(self, teachers):
        """Check and report teacher workload"""
        st.subheader("👨‍🏫 Teacher Workload Analysis")
        
        workload_data = []
        for teacher_id, current_load in self.teacher_workload.items():
            if teacher_id in teachers:
                max_load = teachers[teacher_id]['max_lectures']
                teacher_name = teachers[teacher_id]['name']
                
                workload_data.append({
                    'Teacher ID': teacher_id,
                    'Teacher Name': teacher_name,
                    'Current Load': current_load,
                    'Max Load': max_load,
                    'Utilization (%)': round((current_load / max_load) * 100, 1) if max_load > 0 else 0,
                    'Status': '✅ Optimal' if current_load <= max_load else '⚠️ Overloaded'
                })
        
        if workload_data:
            workload_df = pd.DataFrame(workload_data)
            st.dataframe(workload_df, use_container_width=True)
        else:
            st.info("No workload data available")

# Initialize session state
if 'generator' not in st.se
