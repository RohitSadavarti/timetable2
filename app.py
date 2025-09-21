import streamlit as st
import pandas as pd
import sqlite3
import random
from datetime import datetime, timedelta
import numpy as np
from collections import defaultdict
import os

# Page configuration
st.set_page_config(
    page_title="SQL Database Timetable Generator",
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
</style>
""", unsafe_allow_html=True)

# Title
st.markdown("""
<div class="main-header">
    <h1>🎓 SQL Database Timetable Generator</h1>
    <p>Connect to your existing database and generate optimal timetables</p>
</div>
""", unsafe_allow_html=True)

class SQLTimetableGenerator:
    def __init__(self):
        self.conn = None
        self.db_path = None
        self.timetable = {}
        self.working_days = []
        self.periods_per_day = 6
        self.teacher_workload = defaultdict(int)
        self.class_schedule = defaultdict(lambda: defaultdict(list))
        self.teacher_schedule = defaultdict(lambda: defaultdict(list))
        
    def connect_to_database(self, db_path):
        """Connect to the existing SQLite database"""
        try:
            self.conn = sqlite3.connect(db_path)
            self.db_path = db_path
            # Test connection by getting table names
            cursor = self.conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = cursor.fetchall()
            st.success(f"✅ Connected to database! Found {len(tables)} tables.")
            return True
        except Exception as e:
            st.error(f"❌ Failed to connect to database: {e}")
            return False
    
    def get_database_info(self):
        """Get information about database tables and structure"""
        if not self.conn:
            return None
            
        cursor = self.conn.cursor()
        
        # Get all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
        
        info = {"tables": {}}
        
        for table in tables:
            cursor.execute(f"PRAGMA table_info({table})")
            columns = cursor.fetchall()
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            
            info["tables"][table] = {
                "columns": [col[1] for col in columns],
                "row_count": count
            }
        
        return info
    
    def load_teachers(self):
        """Load teachers from database"""
        cursor = self.conn.cursor()
        
        # Try different possible table names
        possible_tables = ['Teachers_Table', 'Teachers', 'Teacher', 'teachers']
        teachers_data = []
        
        for table_name in possible_tables:
            try:
                cursor.execute(f"SELECT * FROM {table_name}")
                teachers_data = cursor.fetchall()
                # Get column names
                cursor.execute(f"PRAGMA table_info({table_name})")
                columns = [col[1] for col in cursor.fetchall()]
                break
            except:
                continue
        
        if not teachers_data:
            raise Exception("No teachers table found")
            
        teachers = {}
        for row in teachers_data:
            row_dict = dict(zip(columns, row))
            teacher_id = row_dict.get('Teacher_ID') or row_dict.get('teacher_id')
            teachers[teacher_id] = {
                'name': row_dict.get('Teacher_Name') or row_dict.get('teacher_name') or f'Teacher {teacher_id}',
                'max_lectures': row_dict.get('Max_Lectures_Per_Week') or row_dict.get('max_lectures_per_week') or 20,
                'preferred_slots': row_dict.get('Preferred_Slots') or row_dict.get('preferred_slots') or 'Any'
            }
        
        return teachers
    
    def load_subjects(self):
        """Load subjects from database"""
        cursor = self.conn.cursor()
        
        # Try different possible table names
        possible_tables = ['Subjects_Table', 'Subjects', 'Subject', 'subjects']
        subjects_data = []
        
        for table_name in possible_tables:
            try:
                cursor.execute(f"SELECT * FROM {table_name}")
                subjects_data = cursor.fetchall()
                cursor.execute(f"PRAGMA table_info({table_name})")
                columns = [col[1] for col in cursor.fetchall()]
                break
            except:
                continue
        
        if not subjects_data:
            raise Exception("No subjects table found")
            
        subjects = {}
        for row in subjects_data:
            row_dict = dict(zip(columns, row))
            subject_id = row_dict.get('Subject_ID') or row_dict.get('subject_id')
            subjects[subject_id] = {
                'name': row_dict.get('Subject_Name') or row_dict.get('subject_name') or f'Subject {subject_id}',
                'is_common': row_dict.get('Is_Common') or row_dict.get('is_common') == 'Yes',
                'weekly_lectures': row_dict.get('Weekly_Lectures') or row_dict.get('weekly_lectures') or 3
            }
        
        return subjects
    
    def load_classes(self):
        """Load classes from database"""
        cursor = self.conn.cursor()
        
        # Try different possible table names
        possible_tables = ['Classes_Table', 'Classes', 'Class', 'classes']
        classes_data = []
        
        for table_name in possible_tables:
            try:
                cursor.execute(f"SELECT * FROM {table_name}")
                classes_data = cursor.fetchall()
                cursor.execute(f"PRAGMA table_info({table_name})")
                columns = [col[1] for col in cursor.fetchall()]
                break
            except:
                continue
        
        if not classes_data:
            raise Exception("No classes table found")
            
        classes = {}
        for row in classes_data:
            row_dict = dict(zip(columns, row))
            class_id = row_dict.get('Class_ID') or row_dict.get('class_id')
            classes[class_id] = {
                'name': row_dict.get('Class_Name') or row_dict.get('class_name') or class_id,
                'year': row_dict.get('Year') or row_dict.get('year') or 1
            }
        
        return classes
    
    def load_teacher_subject_mapping(self):
        """Load teacher-subject-class mappings"""
        cursor = self.conn.cursor()
        
        # Try different possible table names
        possible_tables = ['Teacher_Subject_Map_Table', 'Teacher_Subject_Map', 'teacher_subject_map']
        mapping_data = []
        
        for table_name in possible_tables:
            try:
                cursor.execute(f"SELECT * FROM {table_name}")
                mapping_data = cursor.fetchall()
                cursor.execute(f"PRAGMA table_info({table_name})")
                columns = [col[1] for col in cursor.fetchall()]
                break
            except:
                continue
        
        if not mapping_data:
            raise Exception("No teacher-subject mapping table found")
        
        mappings = []
        for row in mapping_data:
            row_dict = dict(zip(columns, row))
            mappings.append({
                'teacher_id': row_dict.get('Teacher_ID') or row_dict.get('teacher_id'),
                'class_id': row_dict.get('Class_ID') or row_dict.get('class_id'),
                'subject_id': row_dict.get('Subject_ID') or row_dict.get('subject_id')
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
        if scheduled == total:
            st.success(f"✅ Successfully scheduled all {scheduled} lectures!")
        else:
            st.warning(f"⚠️ Scheduled {scheduled} out of {total} lectures. {total - scheduled} conflicts remain.")
        
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
            max_load = teachers[teacher_id]['max_lectures']
            teacher_name = teachers[teacher_id]['name']
            
            workload_data.append({
                'Teacher ID': teacher_id,
                'Teacher Name': teacher_name,
                'Current Load': current_load,
                'Max Load': max_load,
                'Utilization (%)': round((current_load / max_load) * 100, 1) if max_load > 0 else 0,
                'Status': 'Optimal' if current_load <= max_load else 'Overloaded'
            })
        
        workload_df = pd.DataFrame(workload_data)
        
        # Color code the dataframe
        def highlight_status(val):
            color = 'lightgreen' if val == 'Optimal' else 'lightcoral'
            return f'background-color: {color}'
        
        styled_df = workload_df.style.applymap(highlight_status, subset=['Status'])
        st.dataframe(styled_df, use_container_width=True)

# Initialize session state
if 'generator' not in st.session_state:
    st.session_state.generator = SQLTimetableGenerator()

# Sidebar for database connection
with st.sidebar:
    st.header("🔧 Database Configuration")
    
    # Database connection
    st.subheader("1. Connect to Database")
    
    # Option 1: File upload
    uploaded_db = st.file_uploader(
        "Upload SQLite Database File",
        type=['db', 'sqlite', 'sqlite3'],
        help="Upload your SQLite database file"
    )
    
    if uploaded_db is not None:
        # Save uploaded file temporarily
        with open("temp_database.db", "wb") as f:
            f.write(uploaded_db.getbuffer())
        
        if st.button("📤 Connect to Uploaded DB"):
            success = st.session_state.generator.connect_to_database("temp_database.db")
            if success:
                st.session_state.db_connected = True
    
    # Option 2: File path input
    st.markdown("**OR**")
    db_path = st.text_input(
        "Database File Path",
        placeholder="Enter path to your SQLite database file",
        help="e.g., /path/to/your/database.db"
    )
    
    if st.button("🔗 Connect to Database") and db_path:
        if os.path.exists(db_path):
            success = st.session_state.generator.connect_to_database(db_path)
            if success:
                st.session_state.db_connected = True
        else:
            st.error("Database file not found!")
    
    # Show database info if connected
    if hasattr(st.session_state, 'db_connected') and st.session_state.db_connected:
        st.success("🎉 Database Connected!")
        
        if st.button("📊 Show Database Info"):
            db_info = st.session_state.generator.get_database_info()
            if db_info:
                st.json(db_info)
    
    st.divider()
    
    # Timetable generation settings
    st.subheader("2. Timetable Settings")
    
    # Working days selection
    st.write("**Select Working Days:**")
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
    working_days = []
    
    cols = st.columns(2)
    for i, day in enumerate(days):
        with cols[i % 2]:
            if st.checkbox(day, value=(day != 'Saturday')):
                working_days.append(day)
    
    # Periods per day
    periods_per_day = st.slider("Periods per Day", 4, 8, 6)
    
    # Break periods
    break_periods = st.multiselect(
        "Break Periods",
        options=list(range(1, periods_per_day + 1)),
        default=[4],
        help="Select which periods should be breaks"
    )
    
    # Generate timetable
    if st.button("🎯 Generate Timetable", type="primary"):
        if not hasattr(st.session_state, 'db_connected') or not st.session_state.db_connected:
            st.error("❌ Please connect to database first!")
        elif not working_days:
            st.error("❌ Please select at least one working day!")
        else:
            with st.spinner("Generating timetable..."):
                success = st.session_state.generator.generate_timetable(
                    working_days, periods_per_day, break_periods
                )
                if success:
                    st.session_state.timetable_generated = True

# Main content area
if hasattr(st.session_state, 'timetable_generated') and st.session_state.timetable_generated:
    st.header("📅 Generated Timetable")
    
    # Get classes for tabs
    try:
        _, _, _, classes = st.session_state.generator.get_teaching_assignments()
        
        if classes:
            # Create tabs for each class
            class_tabs = st.tabs(list(classes.keys()))
            
            for i, (class_id, class_data) in enumerate(classes.items()):
                with class_tabs[i]:
                    st.subheader(f"📚 {class_data['name']} - Year {class_data['year']} ({class_id})")
                    
                    if class_id in st.session_state.generator.timetable:
                        # Create timetable dataframe
                        timetable_data = []
                        
                        # Create header
                        headers = ['Day'] + [f'Period {p}\n(P{p})' for p in range(1, st.session_state.generator.periods_per_day + 1)]
                        
                        # Create rows for each day
                        for day in st.session_state.generator.working_days:
                            row = [f"**{day}**"]
                            for period in range(1, st.session_state.generator.periods_per_day + 1):
                                period_key = f'P{period}'
                                slot_data = st.session_state.generator.timetable[class_id][day][period_key]
                                
                                if slot_data['type'] == 'break':
                                    cell_content = f"🍽️ **{slot_data['subject']}**"
                                elif slot_data['type'] == 'lecture':
                                    cell_content = f"📖 **{slot_data['subject']}**\n👨‍🏫 {slot_data['teacher']}"
                                else:
                                    cell_content = f"⭕ {slot_data['subject']}"
                                
                                row.append(cell_content)
                            
                            timetable_data.append(row)
                        
                        # Display as dataframe
                        df = pd.DataFrame(timetable_data, columns=headers)
                        st.dataframe(df, use_container_width=True, height=400)
                        
                        # Download option
                        csv = df.to_csv(index=False)
                        st.download_button(
                            label=f"📥 Download {class_id} Timetable",
                            data=csv,
                            file_name=f"{class_id}_timetable.csv",
                            mime="text/csv"
                        )
    
    except Exception as e:
        st.error(f"Error displaying timetable: {e}")

else:
    st.info("👆 Connect to your database and configure settings to generate timetable")
    
    # Show sample database structure
    st.subheader("📋 Expected Database Structure")
    st.markdown("""
    Your SQLite database should contain these tables:
    
    **1. Teachers_Table / Teachers**
    - Teacher_ID (Primary Key)
    - Teacher_Name  
    - Max_Lectures_Per_Week
    - Preferred_Slots
    
    **2. Subjects_Table / Subjects** 
    - Subject_ID (Primary Key)
    - Subject_Name
    - Is_Common (Yes/No)
    - Weekly_Lectures
    
    **3. Classes_Table / Classes**
    - Class_ID (Primary Key) 
    - Class_Name
    - Year
    
    **4. Teacher_Subject_Map_Table / Teacher_Subject_Map**
    - Teacher_ID (Foreign Key)
    - Class_ID (Foreign Key)  
    - Subject_ID (Foreign Key)
    
    **5. TimeSlots_Table / TimeSlots** (Optional)
    - Slot_ID
    - Day
    - Period_No
    - Start_Time
    - End_Time
    """)

# Footer
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666;'>
    <p>🎓 SQL Database Timetable Generator | Built with Streamlit</p>
    <p><em>Connect to your existing database and generate optimal class schedules!</em></p>
</div>
""", unsafe_allow_html=True)
