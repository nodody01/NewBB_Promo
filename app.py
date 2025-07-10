from flask import Flask, render_template, send_file, request, redirect, url_for, session, flash
import qrcode
import io
import uuid
import os
import sqlite3
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'super_secret_key_192800')  # Безопасный ключ для сессий

# Инициализация базы данных
def init_db():
    with sqlite3.connect('newbb.db') as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS qr_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE,
            promoter_id TEXT,
            created_at TEXT
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS scanned_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT,
            scanned_at TEXT,
            FOREIGN KEY (code) REFERENCES qr_codes (code)
        )''')
        conn.commit()

# Проверка авторизации
def is_authenticated():
    return session.get('authenticated', False)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form.get('password')
        if password == os.getenv('BARMAN_PASSWORD', '192800'):
            session['authenticated'] = True
            return redirect(url_for('scan'))
        else:
            flash('Неверный пароль', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('authenticated', None)
    return redirect(url_for('login'))

@app.route('/generate/<promoter_id>')
def generate_qr(promoter_id):
    # Генерация уникального кода
    guest_code = str(uuid.uuid4())
    
    # Сохранение в базу данных
    with sqlite3.connect('newbb.db') as conn:
        c = conn.cursor()
        c.execute('INSERT INTO qr_codes (code, promoter_id, created_at) VALUES (?, ?, ?)',
                  (guest_code, promoter_id, datetime.now().isoformat()))
        conn.commit()

    # Создание QR-кода
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(guest_code)
    qr.make(fit=True)
    
    # Сохранение QR-кода
    img_io = io.BytesIO()
    img = qr.make_image(fill='black', back_color='white')
    img.save(img_io, 'PNG')
    img_io.seek(0)
    
    filename = f'qr_{guest_code}.png'
    img.save(os.path.join('static', filename))
    
    return render_template('qr.html', guest_code=guest_code, promoter_id=promoter_id, qr_filename=filename)

@app.route('/download/<filename>')
def download_qr(filename):
    return send_file(os.path.join('static', filename), as_attachment=True)

@app.route('/scan')
def scan():
    if not is_authenticated():
        return redirect(url_for('login'))
    return render_template('scan.html')

@app.route('/verify', methods=['POST'])
def verify():
    if not is_authenticated():
        return {"status": "error", "message": "Требуется авторизация"}
    code = request.form.get('code')
    with sqlite3.connect('newbb.db') as conn:
        c = conn.cursor()
        # Проверка существования кода
        c.execute('SELECT promoter_id FROM qr_codes WHERE code = ?', (code,))
        result = c.fetchone()
        if not result:
            return {"status": "error", "message": "QR-код не найден"}
        
        promoter_id = result[0]
        # Проверка, был ли код уже отсканирован
        c.execute('SELECT id FROM scanned_codes WHERE code = ?', (code,))
        if c.fetchone():
            return {"status": "error", "message": "QR-код уже активирован"}
        
        # Сохранение сканирования
        c.execute('INSERT INTO scanned_codes (code, scanned_at) VALUES (?, ?)',
                  (code, datetime.now().isoformat()))
        conn.commit()
        return {"status": "success", "message": f"QR-код успешно активирован. Промоутер: {promoter_id}"}

@app.route('/stats')
def stats():
    if not is_authenticated():
        return redirect(url_for('login'))
    with sqlite3.connect('newbb.db') as conn:
        c = conn.cursor()
        c.execute('''SELECT qr.promoter_id, COUNT(sc.id) as scan_count
                     FROM qr_codes qr
                     LEFT JOIN scanned_codes sc ON qr.code = sc.code
                     GROUP BY qr.promoter_id''')
        stats = c.fetchall()
    return render_template('stats.html', stats=stats)

if __name__ == '__main__':
    os.makedirs('static', exist_ok=True)
    init_db()
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False, ssl_context=('localhost.pem', 'localhost-key.pem'))