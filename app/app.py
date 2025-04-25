import os
import random
from flask import Flask, render_template, request, redirect, url_for, jsonify, send_from_directory
from models import init_db, get_db, Post, get_setting, set_setting
from datetime import datetime, timedelta

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = os.path.abspath(os.path.join(os.path.dirname(__file__), '../posts'))

# Инициализация базы при запуске
init_db()

def process_text(text):
    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
    
    processed = []
    in_blockquote = False
    
    for i, para in enumerate(paragraphs):
        # Обработка первого абзаца
        if i == 0:
            first_paragraph = para.split('\n')
            if len(first_paragraph) >= 1:
                if len(first_paragraph) == 1:
                    processed.append(f"<b><u>{first_paragraph[0]}</u></b>")
                else:
                    processed.append(f"<b><u>{first_paragraph[0]}</u></b>\n{first_paragraph[1]}")
            continue
            
        # Обработка строк с 🧬
        if para.startswith('🧬'):
            processed.append(f"<b>{para}</b>")
            in_blockquote = True
            continue
            
        # Обработка blockquote
        if in_blockquote:
            processed.append(f"<blockquote><i>{para}</i></blockquote>")
            in_blockquote = False
        else:
            processed.append(para)
            
    # Замена упоминаний сервера
    return '\n\n'.join(processed).replace(
        '🍊server', 
        '<a href="https://t.me/mandarin_server">🍊server</a>'
    )


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
        raw_text = request.form['text']
        text = process_text(raw_text)  # Обработка текста
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
        type_ = request.form.get('type', 'regular')
        # Сохраняем в БД только имя папки и тип поста
        c.execute(
            "INSERT INTO posts (text, folder_path, scheduled_at, status, \"order\", type) VALUES (?, ?, ?, ?, ?, ?)",
            (text, folder_name, scheduled_at, 'pending', next_order, type_)
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
    raw_text = data.get('text', '')
    text = process_text(raw_text)  # Обработка текста
    scheduled_at = data.get('scheduled_at')
    type_ = data.get('type', 'regular')
    
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE posts SET text=?, scheduled_at=?, type=? WHERE id=?", 
             (text, scheduled_at, type_, post_id))
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
    if not posts:
        conn.close()
        return redirect(url_for('index'))

    # Разделяем на специальные и обычные
    specials = [p for p in posts if p["type"] == "special"]
    regulars = [p for p in posts if p["type"] != "special"]

    days = (end_date - start_date).days + 1

    # 1. Расставляем специальные посты строго по диапазону
    special_dates = []
    if specials:
        N = len(specials)
        for i, post in enumerate(specials):
            date = start_date + timedelta(days=round(i * (days - 1) / (N - 1) if N > 1 else 0))
            hour = 20
            minute = random.randint(0, 59)
            scheduled_at = datetime.combine(date.date(), datetime.min.time()).replace(hour=hour, minute=minute)
            c.execute("UPDATE posts SET scheduled_at=? WHERE id=?", (scheduled_at.strftime("%Y-%m-%d %H:%M:%S"), post["id"]))
            special_dates.append(scheduled_at)
        special_dates.sort()
    else:
        special_dates = []

    # 2. Расставляем обычные между специальными
    if not specials:
        # Если специальных нет — обычные равномерно по всему диапазону
        total_posts = len(regulars)
        if total_posts > 0:
            for idx, post in enumerate(regulars):
                date = start_date + timedelta(days=round(idx * (days - 1) / (total_posts - 1) if total_posts > 1 else 0))
                hour = 20
                minute = random.randint(0, 59)
                scheduled_at = datetime.combine(date.date(), datetime.min.time()).replace(hour=hour, minute=minute)
                c.execute("UPDATE posts SET scheduled_at=? WHERE id=?", (scheduled_at.strftime("%Y-%m-%d %H:%M:%S"), post["id"]))
    else:
        # Есть специальные — обычные равномерно между ними, по уникальным датам если возможно, не примыкая к спецпостам
        intervals = []
        # Интервал до первого спецпоста
        if special_dates[0].date() > start_date.date():
            intervals.append((start_date, special_dates[0]))
        # Интервалы между спецпостами
        for i in range(len(special_dates) - 1):
            intervals.append((special_dates[i], special_dates[i+1]))
        # Интервал после последнего спецпоста
        if special_dates[-1].date() < end_date.date():
            intervals.append((special_dates[-1], end_date + timedelta(days=0)))

        # Собираем все доступные даты между спецпостами (исключая даты спецпостов и дни, примыкающие к ним)
        available_dates = []
        for a, b in intervals:
            days_in_interval = (b - a).days
            # Только если между спецпостами есть хотя бы 3 дня (иначе некуда вставлять обычные)
            if days_in_interval > 2:
                for d in range(2, days_in_interval):
                    date = a + timedelta(days=d)
                    if date.date() != a.date() and date.date() != b.date():
                        available_dates.append(date)
        
        total_regulars = len(regulars)
        total_dates = len(available_dates)
        
        if total_regulars == 0 or total_dates == 0:
            pass  # Нет обычных постов или нет доступных дат
        elif total_regulars <= total_dates:
            # Назначаем по одной уникальной дате каждому посту
            step = total_dates / total_regulars
            for i in range(total_regulars):
                date_index = int(round(i * step))
                if date_index >= total_dates:  # Защита от выхода за границы
                    date_index = total_dates - 1
                date = available_dates[date_index]
                hour = 20
                minute = random.randint(0, 59)
                scheduled_at = datetime.combine(date.date(), datetime.min.time()).replace(hour=hour, minute=minute)
                c.execute("UPDATE posts SET scheduled_at=? WHERE id=?", (scheduled_at.strftime("%Y-%m-%d %H:%M:%S"), regulars[i]["id"]))
        else:
            # Постов больше, чем дат — распределяем равномерно по кругу
            for i in range(total_regulars):
                date = available_dates[i % total_dates]
                hour = 20
                minute = random.randint(0, 59)
                scheduled_at = datetime.combine(date.date(), datetime.min.time()).replace(hour=hour, minute=minute)
                c.execute("UPDATE posts SET scheduled_at=? WHERE id=?", (scheduled_at.strftime("%Y-%m-%d %H:%M:%S"), regulars[i]["id"]))

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

@app.route('/sort_by_date', methods=['POST'])
def sort_by_date():
    conn = get_db()
    c = conn.cursor()
    # Только неотправленные посты сортируем
    c.execute("SELECT id FROM posts WHERE status != 'sent' ORDER BY scheduled_at ASC, id ASC")
    ids = [row['id'] for row in c.fetchall()]
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
