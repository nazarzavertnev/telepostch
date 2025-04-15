import os
import random
from flask import Flask, render_template, request, redirect, url_for, jsonify, send_from_directory
from models import init_db, get_db, Post, get_setting, set_setting
from datetime import datetime, timedelta

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = os.path.abspath(os.path.join(os.path.dirname(__file__), '../posts'))

# Инициализация базы при запуске
init_db()

def get_media_files(folder_name):
    abs_folder = os.path.join(app.config['UPLOAD_FOLDER'], folder_name)
    if not os.path.exists(abs_folder):
        return []
    files = []
    for fname in os.listdir(abs_folder):
        if fname.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
            files.append(('image', fname))
        elif fname.lower().endswith(('.mp4', '.mov', '.avi', '.webm', '.mkv')):
            files.append(('video', fname))
        else:
            files.append(('file', fname))
    return files

@app.route('/', methods=['GET'])
def index():
    conn = get_db()
    posts = []
    for row in conn.execute("SELECT * FROM posts ORDER BY \"order\" ASC, id ASC"):
        post = Post.from_row(row)
        post.media_files = get_media_files(post.folder_path)
        posts.append(post)
    conn.close()
    # Получаем сохранённые даты дистрибуции
    start_date = get_setting('start_date') or ''
    end_date = get_setting('end_date') or ''
    return render_template('index.html', posts=posts, start_date=start_date, end_date=end_date)

@app.route('/add', methods=['GET', 'POST'])
def add_post():
    if request.method == 'POST':
        text = request.form['text']
        scheduled_at = request.form.get('scheduled_at')
        files = request.files.getlist('media')
        # Определяем максимальный order
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT MAX(\"order\") FROM posts")
        max_order = c.fetchone()[0]
        next_order = (max_order + 1) if max_order is not None else 0
        # Создаём папку для поста (только имя папки)
        folder_name = f'post_{int(datetime.now().timestamp())}'
        post_folder = os.path.join(app.config['UPLOAD_FOLDER'], folder_name)
        os.makedirs(post_folder, exist_ok=True)
        # Сохраняем файлы
        for f in files:
            if f and f.filename:
                f.save(os.path.join(post_folder, f.filename))
        # Сохраняем в БД только имя папки
        c.execute(
            "INSERT INTO posts (text, folder_path, scheduled_at, status, \"order\") VALUES (?, ?, ?, ?, ?)",
            (text, folder_name, scheduled_at, 'pending', next_order)
        )
        conn.commit()
        conn.close()
        return redirect(url_for('index'))
    return render_template('add_post.html')

@app.route('/delete/<int:post_id>', methods=['POST'])
def delete_post(post_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT folder_path FROM posts WHERE id=?", (post_id,))
    row = c.fetchone()
    if row:
        folder_name = row["folder_path"]
        abs_folder = os.path.join(app.config['UPLOAD_FOLDER'], folder_name)
        # Удаляем папку с медиа
        if os.path.exists(abs_folder):
            for fname in os.listdir(abs_folder):
                os.remove(os.path.join(abs_folder, fname))
            os.rmdir(abs_folder)
        c.execute("DELETE FROM posts WHERE id=?", (post_id,))
        conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/edit/<int:post_id>', methods=['POST'])
def edit_post(post_id):
    data = request.json
    text = data.get('text', '')
    scheduled_at = data.get('scheduled_at')
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE posts SET text=?, scheduled_at=? WHERE id=?", (text, scheduled_at, post_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/media/<int:post_id>/<filename>')
def media(post_id, filename):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT folder_path FROM posts WHERE id=?", (post_id,))
    row = c.fetchone()
    conn.close()
    if row:
        folder_name = row["folder_path"]
        abs_folder = os.path.join(app.config['UPLOAD_FOLDER'], folder_name)
        return send_from_directory(abs_folder, filename)
    return "Not found", 404

@app.route('/distribute', methods=['POST'])
def distribute_posts():
    start_date_str = request.form.get('start_date')
    end_date_str = request.form.get('end_date')
    if not start_date_str or not end_date_str:
        return redirect(url_for('index'))
    
    # Сохраняем выбранные даты
    set_setting('start_date', start_date_str)
    set_setting('end_date', end_date_str)

    start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
    end_date = datetime.strptime(end_date_str, "%Y-%m-%d")
    if end_date < start_date:
        return redirect(url_for('index'))

    conn = get_db()
    c = conn.cursor()
    # Только неотправленные посты!
    c.execute("SELECT * FROM posts WHERE status != 'sent' ORDER BY \"order\" ASC, id ASC")
    posts = c.fetchall()
    total_posts = len(posts)
    if total_posts == 0:
        conn.close()
        return redirect(url_for('index'))

    days = (end_date - start_date).days + 1
    if total_posts == 1:
        # Один пост — в первый день
        scheduled_dates = [start_date]
    else:
        # Равномерное распределение постов по диапазону дат
        scheduled_dates = [
            start_date + timedelta(days=round(i * (days - 1) / (total_posts - 1)))
            for i in range(total_posts)
        ]

    for idx, post in enumerate(posts):
        date = scheduled_dates[idx]
        # Случайное время между 20:00 и 21:00
        hour = 20
        minute = random.randint(0, 59)
        scheduled_at = datetime.combine(date.date(), datetime.min.time()).replace(hour=hour, minute=minute)
        c.execute("UPDATE posts SET scheduled_at=? WHERE id=?", (scheduled_at.strftime("%Y-%m-%d %H:%M:%S"), post["id"]))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/reorder_posts', methods=['POST'])
def reorder_posts():
    data = request.get_json()
    ids = data.get('order', [])
    if not ids or not isinstance(ids, list):
        return jsonify({'success': False, 'error': 'Invalid data'}), 400
    conn = get_db()
    c = conn.cursor()
    for idx, post_id in enumerate(ids):
        c.execute('UPDATE posts SET "order"=? WHERE id=?', (idx, post_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/posts')
def api_posts():
    conn = get_db()
    posts = [dict(row) for row in conn.execute("SELECT * FROM posts ORDER BY \"order\" ASC, id ASC")]
    conn.close()
    return jsonify(posts)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
