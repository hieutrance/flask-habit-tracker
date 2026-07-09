from flask import Flask, render_template, request, redirect, url_for, jsonify
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timedelta
import calendar
import os
import json

app = Flask(__name__)

if os.path.exists('firebase_key.json'):
    cred = credentials.Certificate('firebase_key.json')
    firebase_admin.initialize_app(cred)
else:
    firebase_key_env = os.environ.get('FIREBASE_KEY')
    if firebase_key_env:
        firebase_info = json.loads(firebase_key_env)
        cred = credentials.Certificate(firebase_info)
        firebase_admin.initialize_app(cred)
    else:
        raise ValueError("Không tìm thấy file key hoặc biến môi trường FIREBASE_KEY")

db = firestore.client()
HABITS_COLLECTION = "daily_habits"
LOGS_COLLECTION = "habit_logs"

@app.route('/')
def index():
    now = datetime.now()
    today_str = now.strftime('%Y-%m-%d')
    current_year = now.year
    current_month = now.month
    
    # 1. Lấy số ngày trong tháng hiện tại
    _, num_days = calendar.monthrange(current_year, current_month)
    days_in_month = [i for i in range(1, num_days + 1)]
    month_label = now.strftime('%B %Y')

    # 2. Lấy toàn bộ danh sách habits
    habits_ref = db.collection(HABITS_COLLECTION).stream()
    habits_list = []
    for doc in habits_ref:
        h_data = doc.to_dict()
        h_data['id'] = doc.id
        habits_list.append(h_data)

    start_date_str = f"{current_year}-{current_month:02d}-01"
    end_date_str = f"{current_year}-{current_month:02d}-{num_days:02d}"
    
    logs_ref = db.collection(LOGS_COLLECTION)\
        .where("date", ">=", start_date_str)\
        .where("date", "<=", end_date_str).stream()
        
    logs_dict = {day: {} for day in days_in_month}
    total_checkins_this_month = 0
    
    for doc in logs_ref:
        log_data = doc.to_dict()
        log_date = datetime.strptime(log_data['date'], '%Y-%m-%d')
        log_day = log_date.day
        h_id = log_data['habit_id']
        if log_day in logs_dict:
            logs_dict[log_day][h_id] = True
            total_checkins_this_month += 1

    matrix_data = []
    chart_bar_data = {day: 0 for day in days_in_month} 
    
    task_labels = []
    task_counts = []
    
    for habit in habits_list:
        habit_row = {
            "id": habit['id'],
            "title": habit['title'],
            "days": {}
        }
        completed_days_count = 0
        for day in days_in_month:
            is_done = logs_dict[day].get(habit['id'], False)
            habit_row["days"][day] = is_done
            if is_done:
                completed_days_count += 1
                chart_bar_data[day] += 1
                
        habit_row["month_percentage"] = int((completed_days_count / num_days) * 100) if num_days > 0 else 0
        matrix_data.append(habit_row)
        
        # Đẩy dữ liệu vào mảng chart thống kê task
        task_labels.append(habit['title'])
        task_counts.append(completed_days_count)

    this_month_percentage = int((total_checkins_this_month / (len(habits_list) * num_days)) * 100) if habits_list else 0
    
    current_streak = 0
    check_date = now
    while True:
        date_str = check_date.strftime('%Y-%m-%d')
        day_logs = db.collection(LOGS_COLLECTION).where("date", "==", date_str).stream()
        if sum(1 for _ in day_logs) > 0:
            current_streak += 1
            check_date -= timedelta(days=1)
        else:
            break

    recent_days_labels = []
    recent_days_values = []
    for i in range(6, -1, -1):
        d = now - timedelta(days=i)
        recent_days_labels.append(d.strftime('%d/%m'))
        recent_days_values.append(chart_bar_data.get(d.day, 0))

    return render_template(
        'index.html', 
        matrix_data=matrix_data, 
        days_in_month=days_in_month,
        current_day=now.day,
        month_label=month_label,
        current_streak=current_streak,
        this_month_percentage=this_month_percentage,
        total_checkins=total_checkins_this_month,
        recent_days_labels=recent_days_labels,
        recent_days_values=recent_days_values,
        task_labels=task_labels,
        task_counts=task_counts
    )

@app.route('/delete-habit/<habit_id>', methods=['POST'])
def delete_habit(habit_id):
    db.collection(HABITS_COLLECTION).document(habit_id).delete()
    
    logs = db.collection(LOGS_COLLECTION).where("habit_id", "==", habit_id).stream()
    for log in logs:
        db.collection(LOGS_COLLECTION).document(log.id).delete()
        
    return redirect(url_for('index'))

@app.route('/toggle-matrix/<day>/<habit_id>', methods=['POST'])
def toggle_matrix(day, habit_id):
    now = datetime.now()
    target_date_str = f"{now.year}-{now.month:02d}-{int(day):02d}"
    log_doc_id = f"{target_date_str}_{habit_id}"
    log_ref = db.collection(LOGS_COLLECTION).document(log_doc_id)
    
    if log_ref.get().exists:
        log_ref.delete()
    else:
        log_ref.set({
            "habit_id": habit_id,
            "date": target_date_str,
            "completed_at": firestore.SERVER_TIMESTAMP
        })
    return redirect(url_for('index'))

@app.route('/add-habit', methods=['POST'])
def add_habit():
    title = request.form.get('title')
    if title:
        db.collection(HABITS_COLLECTION).add({
            "title": title,
            "created_at": firestore.SERVER_TIMESTAMP
        })
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)