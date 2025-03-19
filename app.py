from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from bs4 import BeautifulSoup
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
import chromedriver_autoinstaller
chromedriver_autoinstaller.install()
import pymysql
import hashlib
import mysql.connector
import requests
import time
import re
from selenium.common.exceptions import TimeoutException



app = Flask(__name__, template_folder='templates')
app.secret_key = 'your_secret_key'


# Fungsi koneksi ke database
def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="scrapping"
    )

db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="",
    database="scrapping"
)
cursor = db.cursor(dictionary=True)

# Route home
@app.route('/')
def home():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

# Route untuk mengecek koneksi database
@app.route('/check_db')
def check_db():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SHOW TABLES")
        tables = cursor.fetchall()
        conn.close()
        return f"Tabel yang tersedia: {tables}"
    except Exception as e:
        return f"Error: {e}"
    
def remove_emojis(text):
    # Regex untuk menghapus emoticon dan karakter non-standar Unicode
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # Emoticon
        "\U0001F300-\U0001F5FF"  # Simbol & Piktogram
        "\U0001F680-\U0001F6FF"  # Transportasi & Simbol lainnya
        "\U0001F1E0-\U0001F1FF"  # Bendera (ISO 3166-1 alpha-2)
        "\U00002702-\U000027B0"  # Simbol tambahan
        "\U000024C2-\U0001F251"  # Simbol tambahan
        "]+", flags=re.UNICODE
    )
    return emoji_pattern.sub(r'', text)  # Menghapus emoticon dari teks
    
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        # Enkripsi password sebelum disimpan
        hashed_password = generate_password_hash(password)
        
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Cek apakah username sudah terdaftar
            cursor.execute("SELECT * FROM login WHERE username = %s", (username,))
            existing_user = cursor.fetchone()
            
            if existing_user:
                flash("Username sudah digunakan, pilih username lain!", "danger")
                return redirect(url_for('register'))

            # Simpan ke database
            cursor.execute("INSERT INTO login (username, password) VALUES (%s, %s)", (username, hashed_password))
            conn.commit()
            conn.close()

            flash("Registrasi berhasil! Silakan login.", "success")
            return redirect(url_for('login'))
        
        except Exception as e:
            flash(f"Terjadi kesalahan: {e}", "danger")
            return redirect(url_for('register'))

    return render_template('register.html')

# Route untuk halaman login 
from werkzeug.security import check_password_hash

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id_user, username, password FROM login WHERE username = %s", (username,))
            user = cursor.fetchone()
            conn.close()

            if user:
                stored_password = user[2]  # Password dari database
                if check_password_hash(stored_password, password):  # Cek password
                    session['user_id'] = user[0]
                    session['username'] = user[1]
                    flash('Login berhasil!', 'success')
                    return redirect(url_for('dashboard'))
                else:
                    flash('Password salah!', 'danger')
            else:
                flash('Username tidak ditemukan!', 'danger')

        except Exception as e:
            flash(f'Error: {str(e)}', 'danger')

    return render_template('login.html')


@app.route('/dashboard')
def dashboard():
    id_user = session.get('user_id')
    if 'user_id' not in session:
        flash('Silakan login terlebih dahulu!', 'warning')
        return redirect(url_for('login'))
    return render_template('dashboard.html',id_user=id_user)

@app.route('/logout')
def logout():
    session.clear()  # Hapus semua session
    return redirect(url_for('login'))

def preprocess_text(text):
    text = text.lower()  # Mengubah ke lowercase
    text = remove_emojis(text)  # Menghapus emoticon
    
   # Mengganti format numbering list (misal: "1." atau "2.") dengan <br><strong>
    text = re.sub(r'(\d+)\.\s+', r'<br><strong>\1.</strong> ', text)
    
    # Mengubah bullet point "-" atau "•" menjadi HTML list
    text = text.replace("\n- ", "<br>• ").replace("\n• ", "<br>• ")

    # Memisahkan berdasarkan double newline "\n\n" untuk paragraf
    paragraphs = text.split("\n\n")  
    paragraphs = [p.strip() for p in paragraphs if p.strip()]  # Hapus spasi kosong
    
    # Menggabungkan paragraf dengan tag HTML agar tampilan tetap rapi
    return "<p>" + "</p><p>".join(paragraphs) + "</p>"
    
    # return text.strip()  # Menghapus spasi berlebih

def scrape_chat_selenium(link):
    options = Options()
    options.headless = True  # Jalankan tanpa membuka jendela browser

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    driver.set_page_load_timeout(60)
    driver.get(link)
    driver.implicitly_wait(5)  # Tunggu elemen termuat

    chat_data = []

    # Ambil semua elemen chat berdasarkan role
    user_messages = driver.find_elements(By.XPATH, '//div[@data-message-author-role="user"]')
    gpt_responses = driver.find_elements(By.XPATH, '//div[@data-message-author-role="assistant"]')

    for user_msg, gpt_msg in zip(user_messages, gpt_responses):
        try:
            # Mengambil teks termasuk emoticon
            prompt = user_msg.get_attribute("innerText").strip()
            response = gpt_msg.get_attribute("innerText").strip()

            chat_data.append({"prompt": prompt, "response": response})
        except Exception as e:
            print(f"⚠️ Error mengambil chat: {e}")

    driver.quit()
    return chat_data

def save_to_database(id_link, chat_data):
    """Menyimpan hasil scraping ke database MySQL."""
    for chat in chat_data:
        prompt = chat["prompt"]
        response = chat["response"]
        cursor.execute("INSERT INTO respon_gpt (id_link, prompt, respon) VALUES (%s, %s, %s)", 
                       (id_link, prompt, response))
        
        prompt_clean = preprocess_text(prompt)
        response_clean = preprocess_text(response)

        # Simpan ke tabel preprocessing
        cursor.execute("INSERT INTO preprocessing (id_link, prompt, respon) VALUES (%s, %s, %s)", 
                       (id_link, prompt_clean, response_clean))

    db.commit()

@app.route('/input_link', methods=['GET','POST'])
def input_link():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    if request.method == 'GET':
        return render_template('input_link.html')
    if request.method == 'POST':
        link = request.form['link']
        user_id = session.get('user_id') 
        
        # Simpan link ke database
        cursor = db.cursor()
        cursor.execute("INSERT INTO link_gpt (link_gpt, id_user) VALUES (%s, %s)", (link, user_id))
        db.commit()
        
        # Ambil ID link yang baru saja dimasukkan
        id_link = cursor.lastrowid
        print(f"✅ Link berhasil disimpan dengan ID: {id_link}")

        # Jalankan scraping chat
        chat_data = scrape_chat_selenium(link)
        print(f"📋 Data hasil scraping: {chat_data}")

        if chat_data:
            for chat in chat_data:
                prompt = chat["prompt"]
                response = chat["response"]
                
                # Simpan chat ke database
                cursor.execute("INSERT INTO respon_gpt (id_link, prompt, respon) VALUES (%s, %s, %s)", (id_link, prompt, response))
                print(f"✅ Data berhasil disimpan: {prompt} -> {response}")

                prompt_clean = preprocess_text(prompt)
                response_clean = preprocess_text(response)

                # Simpan hasil preprocessing ke database preprocessing
                cursor.execute("INSERT INTO preprocessing (id_link, prompt, respon) VALUES (%s, %s, %s)", 
                               (id_link, prompt_clean, response_clean))
                print(f"✅ Data berhasil disimpan di preprocessing: {prompt_clean} -> {response_clean}")

            db.commit()
            print("✅ Semua data berhasil disimpan di respon_gpt!")
        else:
            print("⚠️ Tidak ada chat yang disimpan (chat kosong).")

        cursor.close()
        return redirect(url_for('hasil_scraping', id_link=id_link))

    return render_template('input_link.html')
    
# Halaman Hasil Scraping
@app.route('/hasil_scraping/<int:id_link>')
def hasil_scraping(id_link):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    cursor.execute("SELECT prompt, respon FROM respon_gpt WHERE id_link = %s", (id_link,))
    chats = cursor.fetchall()

    return render_template('scrape.html', chats=chats, id_link=id_link)
# Route untuk menampilkan hasil preprocessing berdasarkan id_link
@app.route('/hasil_preprocessing/<int:id_link>')
def hasil_preprocessing(id_link):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    cursor.execute("SELECT prompt, respon FROM preprocessing WHERE id_link = %s", (id_link,))
    preprocessing_data = cursor.fetchall()

    return render_template('preprocessing.html', preprocessing_data=preprocessing_data, id_link=id_link)

@app.route('/history/<int:id_user>')
def history(id_user):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    query = "SELECT id_link, link_gpt FROM link_gpt WHERE id_user = %s ORDER BY created_at DESC"
    cursor.execute(query, (id_user,))
    data = cursor.fetchall()

    cursor.close()
    conn.close()  # Pastikan koneksi ditutup!

    return render_template('history.html', history_data=data)

if __name__ == '__main__':
    app.run(debug=True)
