import sqlite3
import os
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, session, flash, g, abort, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

DB_PATH = Path("app.bd")

app = Flask(__name__)
app.secret_key = "change-this-secret"  # замените на надёжный секрет

# Конфигурация для загрузки файлов
UPLOAD_FOLDER = 'uploads'
AVATAR_FOLDER = 'static/avatars'
ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx'}
ALLOWED_AVATAR_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'svg'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['AVATAR_FOLDER'] = AVATAR_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Создаем папки для загрузок если их нет
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(AVATAR_FOLDER, exist_ok=True)


def allowed_file(filename):
    """Проверяет, разрешен ли тип файла"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def allowed_avatar_file(filename):
    """Проверяет, разрешен ли тип файла для аватара"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_AVATAR_EXTENSIONS


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        # Включаем внешние ключи для SQLite
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    # Пользователи
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE,
            username TEXT UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('admin','company_hr','university_rep','candidate')),
            created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP)
        )
        """
    )

    # Профили
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS profiles (
            user_id INTEGER PRIMARY KEY,
            first_name TEXT,
            last_name TEXT,
            phone TEXT,
            avatar TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )

    # Компании
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS companies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT,
            logo TEXT,
            contact_user_id INTEGER NOT NULL,
            FOREIGN KEY (contact_user_id) REFERENCES users(id) ON DELETE RESTRICT
        )
        """
    )

    # Вакансии
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS vacancies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            requirements TEXT,
            salary_range TEXT,
            company_id INTEGER NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('on_moderation','published','rejected','archived')),
            created_by INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
            FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE,
            FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE RESTRICT
        )
        """
    )

    # Резюме
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS resumes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            experience TEXT,
            education TEXT,
            resume_file TEXT,
            is_public INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (candidate_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )

    # Навыки и связь многие-ко-многим с резюме
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS skills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS resume_skills (
            resume_id INTEGER NOT NULL,
            skill_id INTEGER NOT NULL,
            PRIMARY KEY (resume_id, skill_id),
            FOREIGN KEY (resume_id) REFERENCES resumes(id) ON DELETE CASCADE,
            FOREIGN KEY (skill_id) REFERENCES skills(id) ON DELETE CASCADE
        )
        """
    )

    # Отклики на вакансии
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vacancy_id INTEGER NOT NULL,
            candidate_id INTEGER NOT NULL,
            resume_id INTEGER,
            status TEXT NOT NULL CHECK (status IN ('new','viewed','interview','rejected')),
            cover_letter TEXT,
            created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
            FOREIGN KEY (vacancy_id) REFERENCES vacancies(id) ON DELETE CASCADE,
            FOREIGN KEY (candidate_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (resume_id) REFERENCES resumes(id) ON DELETE SET NULL
        )
        """
    )

    # Заявки на стажировки
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS internship_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            university_id INTEGER NOT NULL,
            specialization TEXT,
            student_count INTEGER,
            period_start TEXT,
            period_end TEXT,
            skills_required TEXT,
            status TEXT NOT NULL CHECK (status IN ('on_moderation','published')),
            created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
            FOREIGN KEY (university_id) REFERENCES users(id) ON DELETE RESTRICT
        )
        """
    )

    # Отклики компаний на стажировки
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS internship_responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            internship_request_id INTEGER NOT NULL,
            company_id INTEGER NOT NULL,
            message TEXT,
            status TEXT,
            FOREIGN KEY (internship_request_id) REFERENCES internship_requests(id) ON DELETE CASCADE,
            FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE
        )
        """
    )

    # Полезные индексы
    db.execute("CREATE INDEX IF NOT EXISTS idx_users_role ON users(role)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_companies_contact ON companies(contact_user_id)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_vacancies_company ON vacancies(company_id)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_vacancies_status ON vacancies(status)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_resumes_candidate ON resumes(candidate_id)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_applications_vacancy ON applications(vacancy_id)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_applications_candidate ON applications(candidate_id)")
    
    # Миграция: добавляем created_at в internship_requests если его нет
    try:
        db.execute("ALTER TABLE internship_requests ADD COLUMN created_at TEXT DEFAULT (CURRENT_TIMESTAMP)")
        db.commit()
    except sqlite3.OperationalError:
        # Колонка уже существует, игнорируем ошибку
        pass
    
    # Миграция: добавляем недостающие поля в profiles если их нет
    try:
        db.execute("ALTER TABLE profiles ADD COLUMN phone TEXT")
        db.commit()
    except sqlite3.OperationalError:
        # Колонка уже существует, игнорируем ошибку
        pass
    
    # Логи модерации
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS moderation_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_type TEXT NOT NULL CHECK (item_type IN ('vacancy','internship')),
            item_id INTEGER NOT NULL,
            action TEXT NOT NULL CHECK (action IN ('approve','reject','delete')),
            moderator_id INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
            note TEXT,
            FOREIGN KEY (moderator_id) REFERENCES users(id) ON DELETE SET NULL
        )
        """
    )
    db.commit()


def setup():
    init_db()
    # При первом запуске создадим пользователя-админа, если его нет
    db = get_db()
    cur = db.execute("SELECT 1 FROM users WHERE username = ?", ("admin",))
    if cur.fetchone() is None:
        db.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            ("admin", generate_password_hash("admin"), "admin"),
        )
        db.commit()

    # Создадим дефолтного пользователя university_rep
    cur = db.execute("SELECT id FROM users WHERE username = ?", ("university_rep",))
    uni = cur.fetchone()
    if uni is None:
        db.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            ("university_rep", generate_password_hash("university_rep"), "university_rep"),
        )
        db.commit()
        uni_id = db.execute("SELECT id FROM users WHERE username = ?", ("university_rep",)).fetchone()[0]
    else:
        uni_id = uni["id"]
    # Создадим/обеспечим компанию, к которой можно будет привязывать вакансии университета
    cur = db.execute("SELECT id FROM companies WHERE contact_user_id = ?", (uni_id,))
    if cur.fetchone() is None:
        db.execute(
            "INSERT INTO companies (name, description, logo, contact_user_id) VALUES (?, ?, ?, ?)",
            (f"Company of university_rep", "Автосоздано для публикации вакансий университетом", None, uni_id),
        )
        db.commit()

    # Создадим дефолтного пользователя company_hr
    cur = db.execute("SELECT id FROM users WHERE username = ?", ("company_hr",))
    hr = cur.fetchone()
    if hr is None:
        db.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            ("company_hr", generate_password_hash("company_hr"), "company_hr"),
        )
        db.commit()
        hr_id = db.execute("SELECT id FROM users WHERE username = ?", ("company_hr",)).fetchone()[0]
    else:
        hr_id = hr["id"]
    # Создадим/обеспечим компанию для HR
    cur = db.execute("SELECT id FROM companies WHERE contact_user_id = ?", (hr_id,))
    if cur.fetchone() is None:
        db.execute(
            "INSERT INTO companies (name, description, logo, contact_user_id) VALUES (?, ?, ?, ?)",
            (f"HR Company", "Компания для HR-менеджера", None, hr_id),
        )
        db.commit()


def login_required(view_func):
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("Требуется вход.", "warning")
            return redirect(url_for("login"))
        return view_func(*args, **kwargs)
    wrapper.__name__ = view_func.__name__
    return wrapper


def role_required(*roles):
    def decorator(view_func):
        def wrapper(*args, **kwargs):
            if "user_id" not in session:
                flash("Требуется вход.", "warning")
                return redirect(url_for("login"))
            if session.get("role") not in roles:
                flash("Недостаточно прав.", "danger")
                return redirect(url_for("dashboard"))
            return view_func(*args, **kwargs)
        wrapper.__name__ = view_func.__name__
        return wrapper
    return decorator


@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""

        if not username or not password:
            flash("Введите логин и пароль.", "warning")
            return render_template("login.html")

        db = get_db()
        user = db.execute(
            "SELECT id, username, password_hash, role FROM users WHERE username = ?",
            (username,),
        ).fetchone()

        if not user or not check_password_hash(user["password_hash"], password):
            flash("Неверный логин или пароль.", "danger")
            return render_template("login.html")

        # Сверка роли: берём роль из БД и сохраняем в сессии
        session["user_id"] = user["id"]
        session["username"] = user["username"]
        session["role"] = user["role"]
        flash("Успешный вход.", "success")
        return redirect(url_for("dashboard"))

    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        email = (request.form.get("email") or "").strip()
        first_name = (request.form.get("first_name") or "").strip()
        last_name = (request.form.get("last_name") or "").strip()
        phone = (request.form.get("phone") or "").strip()
        password = request.form.get("password") or ""
        password_confirm = request.form.get("password_confirm") or ""

        if not username or not email or not password:
            flash("Заполните все обязательные поля.", "warning")
            return render_template("register.html")

        if password != password_confirm:
            flash("Пароли не совпадают.", "warning")
            return render_template("register.html")

        db = get_db()
        try:
            # Создаём пользователя с ролью candidate по умолчанию
            user_id = db.execute(
                "INSERT INTO users (username, email, password_hash, role) VALUES (?, ?, ?, ?)",
                (username, email, generate_password_hash(password), "candidate"),
            ).lastrowid
            db.commit()
            
            # Создаём профиль
            db.execute(
                "INSERT INTO profiles (user_id, first_name, last_name, phone) VALUES (?, ?, ?, ?)",
                (user_id, first_name, last_name, phone),
            )
            db.commit()
        except sqlite3.IntegrityError:
            flash("Логин или email уже заняты.", "danger")
            return render_template("register.html")

        flash("Регистрация успешна. Войдите.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Вы вышли из системы.", "info")
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    db = get_db()
    # Получаем информацию о пользователе и его профиле
    user_info = db.execute(
        "SELECT u.id, u.username, u.email, u.role, u.created_at, p.first_name, p.last_name, p.phone, p.avatar "
        "FROM users u LEFT JOIN profiles p ON u.id = p.user_id WHERE u.id = ?",
        (session.get("user_id"),)
    ).fetchone()
    
    return render_template("dashboard.html", user=user_info)


@app.route("/admin")
@role_required("admin")
def admin_only():
    return render_template("admin.html", username=session.get("username"))
    

# -------------------- Модерация (Admin) --------------------
@app.route("/admin/moderation")
@role_required("admin")
def admin_moderation():
    tab = request.args.get("tab", "vacancies")
    page = max(int(request.args.get("page", 1) or 1), 1)
    per_page = min(max(int(request.args.get("per_page", 10) or 10), 1), 50)
    offset = (page - 1) * per_page
    db = get_db()

    # Фильтры
    company_q = (request.args.get("company") or "").strip()
    university_q = (request.args.get("university") or "").strip()
    status_q = (request.args.get("status") or "on_moderation").strip()

    vac_sql = (
        "SELECT v.id, v.title, v.description, v.status, v.created_at, c.name AS company_name "
        "FROM vacancies v JOIN companies c ON v.company_id = c.id "
        "WHERE v.status = ? AND (? = '' OR c.name LIKE '%' || ? || '%') "
        "ORDER BY v.created_at DESC LIMIT ? OFFSET ?"
    )
    vacancies = db.execute(vac_sql, (status_q, company_q, company_q, per_page, offset)).fetchall()

    vac_count = db.execute(
        "SELECT COUNT(*) FROM vacancies v JOIN companies c ON v.company_id=c.id WHERE v.status = ? AND (? = '' OR c.name LIKE '%' || ? || '%')",
        (status_q, company_q, company_q),
    ).fetchone()[0]

    int_sql = (
        "SELECT ir.id, ir.specialization, ir.student_count, ir.status, ir.period_start, ir.period_end, u.username AS university_name "
        "FROM internship_requests ir JOIN users u ON ir.university_id = u.id "
        "WHERE ir.status = ? AND (? = '' OR u.username LIKE '%' || ? || '%') "
        "ORDER BY ir.id DESC LIMIT ? OFFSET ?"
    )
    internship_requests = db.execute(int_sql, (status_q, university_q, university_q, per_page, offset)).fetchall()

    int_count = db.execute(
        "SELECT COUNT(*) FROM internship_requests ir JOIN users u ON ir.university_id=u.id WHERE ir.status = ? AND (? = '' OR u.username LIKE '%' || ? || '%')",
        (status_q, university_q, university_q),
    ).fetchone()[0]
    return render_template(
        "moderation.html",
        tab=tab,
        vacancies=vacancies,
        internship_requests=internship_requests,
        page=page,
        per_page=per_page,
        vac_total=vac_count,
        int_total=int_count,
        status_q=status_q,
        company_q=company_q,
        university_q=university_q,
    )


@app.post("/admin/moderation/vacancy/<int:vacancy_id>/approve")
@role_required("admin")
def approve_vacancy(vacancy_id: int):
    db = get_db()
    row = db.execute("SELECT id FROM vacancies WHERE id = ?", (vacancy_id,)).fetchone()
    if not row:
        abort(404, description="Vacancy not found")
    db.execute("UPDATE vacancies SET status = 'published' WHERE id = ?", (vacancy_id,))
    db.execute(
        "INSERT INTO moderation_logs (item_type, item_id, action, moderator_id) VALUES (?,?,?,?)",
        ("vacancy", vacancy_id, "approve", session.get("user_id")),
    )
    db.commit()
    flash("Вакансия одобрена и опубликована.", "success")
    return redirect(url_for("admin_moderation", tab="vacancies"))


@app.post("/admin/moderation/vacancy/<int:vacancy_id>/reject")
@role_required("admin")
def reject_vacancy(vacancy_id: int):
    db = get_db()
    row = db.execute("SELECT id FROM vacancies WHERE id = ?", (vacancy_id,)).fetchone()
    if not row:
        abort(404, description="Vacancy not found")
    db.execute("UPDATE vacancies SET status = 'rejected' WHERE id = ?", (vacancy_id,))
    db.execute(
        "INSERT INTO moderation_logs (item_type, item_id, action, moderator_id) VALUES (?,?,?,?)",
        ("vacancy", vacancy_id, "reject", session.get("user_id")),
    )
    db.commit()
    flash("Вакансия отклонена.", "info")
    return redirect(url_for("admin_moderation", tab="vacancies"))


@app.post("/admin/moderation/vacancy/<int:vacancy_id>/delete")
@role_required("admin")
def delete_vacancy(vacancy_id: int):
    db = get_db()
    row = db.execute("SELECT id, status FROM vacancies WHERE id = ?", (vacancy_id,)).fetchone()
    if not row:
        abort(404, description="Vacancy not found")
    if row["status"] == "on_moderation":
        abort(400, description="Cannot delete item on moderation")
    db.execute("DELETE FROM vacancies WHERE id = ?", (vacancy_id,))
    db.execute(
        "INSERT INTO moderation_logs (item_type, item_id, action, moderator_id) VALUES (?,?,?,?)",
        ("vacancy", vacancy_id, "delete", session.get("user_id")),
    )
    db.commit()
    flash("Вакансия удалена (если она была не на модерации).", "warning")
    return redirect(url_for("admin_moderation", tab="vacancies"))


@app.post("/admin/moderation/internship/<int:req_id>/approve")
@role_required("admin")
def approve_internship(req_id: int):
    db = get_db()
    row = db.execute("SELECT id FROM internship_requests WHERE id = ?", (req_id,)).fetchone()
    if not row:
        abort(404, description="Internship request not found")
    db.execute("UPDATE internship_requests SET status = 'published' WHERE id = ?", (req_id,))
    db.execute(
        "INSERT INTO moderation_logs (item_type, item_id, action, moderator_id) VALUES (?,?,?,?)",
        ("internship", req_id, "approve", session.get("user_id")),
    )
    db.commit()
    flash("Заявка на стажировку опубликована.", "success")
    return redirect(url_for("admin_moderation", tab="internships"))


@app.post("/admin/moderation/internship/<int:req_id>/reject")
@role_required("admin")
def reject_internship(req_id: int):
    db = get_db()
    row = db.execute("SELECT id FROM internship_requests WHERE id = ?", (req_id,)).fetchone()
    if not row:
        abort(404, description="Internship request not found")
    db.execute("UPDATE internship_requests SET status = 'rejected' WHERE id = ?", (req_id,))
    db.execute(
        "INSERT INTO moderation_logs (item_type, item_id, action, moderator_id) VALUES (?,?,?,?)",
        ("internship", req_id, "reject", session.get("user_id")),
    )
    db.commit()
    flash("Заявка на стажировку отклонена.", "info")
    return redirect(url_for("admin_moderation", tab="internships"))


@app.post("/admin/moderation/internship/<int:req_id>/delete")
@role_required("admin")
def delete_internship(req_id: int):
    db = get_db()
    row = db.execute("SELECT id, status FROM internship_requests WHERE id = ?", (req_id,)).fetchone()
    if not row:
        abort(404, description="Internship request not found")
    if row["status"] == "on_moderation":
        abort(400, description="Cannot delete item on moderation")
    db.execute("DELETE FROM internship_requests WHERE id = ?", (req_id,))
    db.execute(
        "INSERT INTO moderation_logs (item_type, item_id, action, moderator_id) VALUES (?,?,?,?)",
        ("internship", req_id, "delete", session.get("user_id")),
    )
    db.commit()
    flash("Заявка удалена (если она была рассмотрена).", "warning")
    return redirect(url_for("admin_moderation", tab="internships"))


# -------------------- Каталог вакансий и стажировок --------------------
@app.route("/catalog")
@login_required
def catalog():
    db = get_db()
    # Получаем опубликованные вакансии
    vacancies = db.execute(
        "SELECT v.id, v.title, v.description, v.salary_range, c.name AS company_name, v.created_at "
        "FROM vacancies v JOIN companies c ON v.company_id = c.id "
        "WHERE v.status = 'published' ORDER BY v.created_at DESC"
    ).fetchall()
    
    # Получаем опубликованные стажировки
    internships = db.execute(
        "SELECT ir.id, ir.specialization, ir.student_count, ir.period_start, ir.period_end, u.username AS university_name "
        "FROM internship_requests ir JOIN users u ON ir.university_id = u.id "
        "WHERE ir.status = 'published' ORDER BY ir.id DESC"
    ).fetchall()
    
    return render_template("catalog.html", vacancies=vacancies)


@app.route("/vacancy/<int:vacancy_id>")
@login_required
def vacancy_detail(vacancy_id):
    db = get_db()
    vacancy = db.execute(
        "SELECT v.*, c.name AS company_name FROM vacancies v JOIN companies c ON v.company_id = c.id WHERE v.id = ? AND v.status = 'published'",
        (vacancy_id,),
    ).fetchone()
    if not vacancy:
        abort(404)
    return render_template("vacancy_detail.html", vacancy=vacancy)


@app.route("/vacancy/<int:vacancy_id>/apply", methods=["GET", "POST"])
@login_required
def apply_to_vacancy(vacancy_id):
    db = get_db()
    vacancy = db.execute(
        "SELECT v.*, c.name AS company_name FROM vacancies v JOIN companies c ON v.company_id = c.id WHERE v.id = ? AND v.status = 'published'",
        (vacancy_id,),
    ).fetchone()
    if not vacancy:
        abort(404)
    
    if request.method == "POST":
        cover_letter = (request.form.get("cover_letter") or "").strip()
        
        # Получаем данные из формы
        first_name = (request.form.get("first_name") or "").strip()
        last_name = (request.form.get("last_name") or "").strip()
        age = request.form.get("age")
        city = (request.form.get("city") or "").strip()
        education = (request.form.get("education") or "").strip()
        experience = (request.form.get("experience") or "").strip()
        skills = (request.form.get("skills") or "").strip()
        
        if not first_name or not last_name:
            flash("Заполните обязательные поля (имя и фамилия).", "warning")
            return render_template("apply_to_vacancy.html", vacancy=vacancy)
        
        # Обработка загрузки файла резюме (опционально)
        resume_file = request.files.get("resume_file")
        resume_file_path = None
        
        if resume_file and resume_file.filename:
            if not allowed_file(resume_file.filename):
                flash("Недопустимый формат файла. Разрешены только PDF, DOC и DOCX файлы.", "warning")
                return render_template("apply_to_vacancy.html", vacancy=vacancy)
            
            # Сохраняем файл на сервер
            filename = secure_filename(resume_file.filename)
            resume_file_path = os.path.join(app.config['UPLOAD_FOLDER'], f"resume_{session.get('user_id')}_{vacancy_id}_{filename}")
            resume_file.save(resume_file_path)
        
        # Создаём резюме в БД с данными из анкеты и опциональным файлом
        resume_id = db.execute(
            "INSERT INTO resumes (candidate_id, title, experience, education, resume_file, is_public) VALUES (?, ?, ?, ?, ?, ?)",
            (session.get("user_id"), f"{first_name} {last_name}", experience, education, resume_file_path, 1),
        ).lastrowid
        db.commit()
        
        # Создаём отклик
        db.execute(
            "INSERT INTO applications (vacancy_id, candidate_id, resume_id, status, cover_letter) VALUES (?, ?, ?, 'new', ?)",
            (vacancy_id, session.get("user_id"), resume_id, cover_letter),
        )
        db.commit()
        
        flash("Отклик отправлен! HR компании получит уведомление.", "success")
        return redirect(url_for("application_success", vacancy_id=vacancy_id))
    
    return render_template("apply_to_vacancy.html", vacancy=vacancy)


# -------------------- Кабинет HR --------------------
@app.route("/hr")
@role_required("company_hr")
def hr_dashboard():
    db = get_db()
    # Получаем вакансии компании
    company = db.execute(
        "SELECT id FROM companies WHERE contact_user_id = ?",
        (session.get("user_id"),),
    ).fetchone()
    
    vacancies = db.execute(
        "SELECT v.*, COUNT(a.id) as application_count FROM vacancies v LEFT JOIN applications a ON v.id = a.vacancy_id WHERE v.company_id = ? GROUP BY v.id ORDER BY v.created_at DESC",
        (company["id"],),
    ).fetchall()
    
    # Получаем отклики на вакансии компании
    applications = db.execute(
        "SELECT a.*, v.title as vacancy_title, u.username as candidate_name FROM applications a JOIN vacancies v ON a.vacancy_id = v.id JOIN users u ON a.candidate_id = u.id WHERE v.company_id = ? ORDER BY a.created_at DESC",
        (company["id"],),
    ).fetchall()
    
    return render_template("hr_dashboard.html", vacancies=vacancies, applications=applications)


@app.route("/hr/vacancies/new", methods=["GET", "POST"])
@role_required("company_hr")
def hr_create_vacancy():
    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        description = (request.form.get("description") or "").strip()
        requirements = (request.form.get("requirements") or "").strip()
        salary_range = (request.form.get("salary_range") or "").strip()
        contacts = (request.form.get("contacts") or "").strip()
        
        if not title:
            flash("Укажите название вакансии.", "warning")
            return render_template("hr_vacancy_create.html")
        
        db = get_db()
        company = db.execute(
            "SELECT id FROM companies WHERE contact_user_id = ?",
            (session.get("user_id"),),
        ).fetchone()
        
        db.execute(
            "INSERT INTO vacancies (title, description, requirements, salary_range, company_id, status, created_by) VALUES (?, ?, ?, ?, ?, 'on_moderation', ?)",
            (title, description, requirements, salary_range, company["id"], session.get("user_id")),
        )
        db.commit()
        
        flash("Вакансия отправлена на модерацию.", "success")
        return redirect(url_for("hr_dashboard"))
    
    return render_template("hr_vacancy_create.html")


@app.route("/application/success/<int:vacancy_id>")
@login_required
def application_success(vacancy_id):
    db = get_db()
    vacancy = db.execute(
        "SELECT v.title, c.name AS company_name FROM vacancies v JOIN companies c ON v.company_id = c.id WHERE v.id = ?",
        (vacancy_id,),
    ).fetchone()
    if not vacancy:
        abort(404)
    return render_template("application_success.html", vacancy=vacancy)


@app.route("/hr/applications/<int:application_id>")
@role_required("company_hr")
def hr_view_application(application_id):
    db = get_db()
    application = db.execute(
        "SELECT a.*, v.title as vacancy_title, u.username as candidate_name, p.first_name, p.last_name, p.phone, r.id as resume_id, r.title as resume_title, r.experience, r.education, r.resume_file "
        "FROM applications a "
        "JOIN vacancies v ON a.vacancy_id = v.id "
        "JOIN users u ON a.candidate_id = u.id "
        "LEFT JOIN profiles p ON u.id = p.user_id "
        "LEFT JOIN resumes r ON a.resume_id = r.id "
        "WHERE a.id = ? AND v.company_id IN (SELECT id FROM companies WHERE contact_user_id = ?)",
        (application_id, session.get("user_id")),
    ).fetchone()
    if not application:
        abort(404)
    return render_template("hr_application_detail.html", application=application)


@app.route("/hr/resume/<int:resume_id>/download")
@role_required("company_hr")
def hr_download_resume(resume_id):
    db = get_db()
    # Проверяем, что резюме принадлежит отклику на вакансию компании HR
    resume = db.execute(
        "SELECT r.resume_file, r.title FROM resumes r "
        "JOIN applications a ON r.id = a.resume_id "
        "JOIN vacancies v ON a.vacancy_id = v.id "
        "WHERE r.id = ? AND v.company_id IN (SELECT id FROM companies WHERE contact_user_id = ?)",
        (resume_id, session.get("user_id")),
    ).fetchone()
    
    if not resume or not resume["resume_file"]:
        abort(404, description="Resume file not found")
    
    # Проверяем, что файл существует
    if not os.path.exists(resume["resume_file"]):
        abort(404, description="Resume file not found on disk")
    
    # Получаем оригинальное имя файла из пути
    original_filename = os.path.basename(resume["resume_file"])
    
    # Убираем префикс с ID пользователя и вакансии для более читаемого имени
    # Формат: resume_userId_vacancyId_originalname
    if original_filename.startswith("resume_") and "_" in original_filename:
        parts = original_filename.split('_', 3)  # resume, userId, vacancyId, originalname
        if len(parts) >= 4:
            original_filename = parts[3]
        elif len(parts) == 3:
            # Если нет оригинального имени, используем название резюме
            original_filename = f"{resume['title']}.pdf"
    
    # Если не удалось извлечь оригинальное имя, используем название резюме
    if not original_filename or original_filename == os.path.basename(resume["resume_file"]):
        # Определяем расширение из оригинального файла
        file_ext = os.path.splitext(resume["resume_file"])[1]
        original_filename = f"{resume['title']}{file_ext}"
    
    # Отправляем файл
    return send_file(resume["resume_file"], as_attachment=True, download_name=original_filename)


@app.route("/hr/resume/<int:resume_id>/view")
@role_required("company_hr")
def hr_view_resume(resume_id):
    db = get_db()
    # Проверяем, что резюме принадлежит отклику на вакансию компании HR
    resume = db.execute(
        "SELECT r.id, r.resume_file, r.title, r.experience, r.education FROM resumes r "
        "JOIN applications a ON r.id = a.resume_id "
        "JOIN vacancies v ON a.vacancy_id = v.id "
        "WHERE r.id = ? AND v.company_id IN (SELECT id FROM companies WHERE contact_user_id = ?)",
        (resume_id, session.get("user_id")),
    ).fetchone()
    
    if not resume:
        abort(404, description="Resume not found")
    
    return render_template("hr_resume_view.html", resume=resume)


@app.route("/hr/vacancies/<int:vacancy_id>/close", methods=["POST"])
@role_required("company_hr")
def hr_close_vacancy(vacancy_id):
    db = get_db()
    # Проверяем, что вакансия принадлежит компании HR
    vacancy = db.execute(
        "SELECT id FROM vacancies WHERE id = ? AND company_id IN (SELECT id FROM companies WHERE contact_user_id = ?)",
        (vacancy_id, session.get("user_id")),
    ).fetchone()
    if not vacancy:
        abort(404)
    
    # Закрываем вакансию (архивируем)
    db.execute(
        "UPDATE vacancies SET status = 'archived' WHERE id = ?",
        (vacancy_id,),
    )
    db.commit()
    
    flash("Вакансия закрыта и перемещена в архив.", "success")
    return redirect(url_for("hr_dashboard"))


# Детали для модерации
@app.route("/admin/moderation/vacancy/<int:vacancy_id>")
@role_required("admin")
def admin_vacancy_detail(vacancy_id: int):
    db = get_db()
    v = db.execute(
        "SELECT v.*, c.name AS company_name FROM vacancies v JOIN companies c ON v.company_id=c.id WHERE v.id = ?",
        (vacancy_id,),
    ).fetchone()
    if not v:
        abort(404)
    return render_template("moderation_vacancy_detail.html", v=v)


@app.route("/admin/moderation/internship/<int:req_id>")
@role_required("admin")
def internship_detail(req_id: int):
    db = get_db()
    r = db.execute(
        "SELECT ir.*, u.username AS university_name FROM internship_requests ir JOIN users u ON ir.university_id=u.id WHERE ir.id = ?",
        (req_id,),
    ).fetchone()
    if not r:
        abort(404)
    return render_template("moderation_internship_detail.html", r=r)


# -------------------- Кабинет Университета --------------------
@app.route("/university")
@role_required("university_rep")
def university_dashboard():
    db = get_db()
    # Получаем одобренные стажировки
    approved_internships = db.execute(
        "SELECT ir.*, u.username AS university_name FROM internship_requests ir JOIN users u ON ir.university_id = u.id WHERE ir.status = 'published' ORDER BY ir.id DESC"
    ).fetchall()
    return render_template("university.html", username=session.get("username"), approved_internships=approved_internships)


@app.route("/university/internship_requests/new", methods=["GET", "POST"])
@role_required("university_rep")
def create_internship_request():
    if request.method == "POST":
        specialization = (request.form.get("specialization") or "").strip()
        student_count = int(request.form.get("student_count") or 0)
        period_start = (request.form.get("period_start") or "").strip()
        period_end = (request.form.get("period_end") or "").strip()
        skills_required = (request.form.get("skills_required") or "").strip()
        if not specialization:
            flash("Укажите специализацию.", "warning")
            return render_template("internship_request_create.html")
        db = get_db()
        db.execute(
            "INSERT INTO internship_requests (university_id, specialization, student_count, period_start, period_end, skills_required, status) VALUES (?,?,?,?,?,?, 'on_moderation')",
            (session.get("user_id"), specialization, student_count, period_start, period_end, skills_required),
        )
        db.commit()
        flash("Заявка отправлена на модерацию.", "success")
        return redirect(url_for("university_dashboard"))
    return render_template("internship_request_create.html")


# -------------------- Редактирование профиля --------------------
@app.route("/profile/edit", methods=["GET", "POST"])
@login_required
def edit_profile():
    db = get_db()
    
    if request.method == "POST":
        first_name = (request.form.get("first_name") or "").strip()
        last_name = (request.form.get("last_name") or "").strip()
        phone = (request.form.get("phone") or "").strip()
        email = (request.form.get("email") or "").strip()
        
        # Обработка загрузки аватара
        avatar_file = request.files.get("avatar")
        avatar_path = None
        
        if avatar_file and avatar_file.filename:
            if not allowed_avatar_file(avatar_file.filename):
                flash("Недопустимый формат файла аватара. Разрешены только PNG, JPG, JPEG, GIF, SVG.", "warning")
                return redirect(url_for("edit_profile"))
            
            # Сохраняем аватар
            filename = secure_filename(avatar_file.filename)
            avatar_path = os.path.join(app.config['AVATAR_FOLDER'], f"avatar_{session.get('user_id')}_{filename}")
            avatar_file.save(avatar_path)
        
        try:
            # Обновляем email в таблице users
            if email:
                db.execute("UPDATE users SET email = ? WHERE id = ?", (email, session.get("user_id")))
            
            # Обновляем или создаем профиль
            existing_profile = db.execute("SELECT user_id FROM profiles WHERE user_id = ?", (session.get("user_id"),)).fetchone()
            
            if existing_profile:
                # Обновляем существующий профиль
                if avatar_path:
                    db.execute(
                        "UPDATE profiles SET first_name = ?, last_name = ?, phone = ?, avatar = ? WHERE user_id = ?",
                        (first_name, last_name, phone, avatar_path, session.get("user_id"))
                    )
                else:
                    db.execute(
                        "UPDATE profiles SET first_name = ?, last_name = ?, phone = ? WHERE user_id = ?",
                        (first_name, last_name, phone, session.get("user_id"))
                    )
            else:
                # Создаем новый профиль
                db.execute(
                    "INSERT INTO profiles (user_id, first_name, last_name, phone, avatar) VALUES (?, ?, ?, ?, ?)",
                    (session.get("user_id"), first_name, last_name, phone, avatar_path)
                )
            
            db.commit()
            flash("Профиль успешно обновлен.", "success")
            return redirect(url_for("dashboard"))
            
        except sqlite3.IntegrityError:
            flash("Email уже используется другим пользователем.", "danger")
            return redirect(url_for("edit_profile"))
    
    # Получаем текущую информацию о пользователе
    user_info = db.execute(
        "SELECT u.id, u.username, u.email, u.role, p.first_name, p.last_name, p.phone, p.avatar "
        "FROM users u LEFT JOIN profiles p ON u.id = p.user_id WHERE u.id = ?",
        (session.get("user_id"),)
    ).fetchone()
    
    return render_template("edit_profile.html", user=user_info)


@app.route("/profile/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current_password = request.form.get("current_password") or ""
        new_password = request.form.get("new_password") or ""
        confirm_password = request.form.get("confirm_password") or ""
        
        if not current_password or not new_password or not confirm_password:
            flash("Заполните все поля.", "warning")
            return render_template("change_password.html")
        
        if new_password != confirm_password:
            flash("Новые пароли не совпадают.", "warning")
            return render_template("change_password.html")
        
        if len(new_password) < 6:
            flash("Пароль должен содержать минимум 6 символов.", "warning")
            return render_template("change_password.html")
        
        db = get_db()
        user = db.execute(
            "SELECT password_hash FROM users WHERE id = ?",
            (session.get("user_id"),)
        ).fetchone()
        
        if not user or not check_password_hash(user["password_hash"], current_password):
            flash("Неверный текущий пароль.", "danger")
            return render_template("change_password.html")
        
        # Обновляем пароль
        db.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (generate_password_hash(new_password), session.get("user_id"))
        )
        db.commit()
        
        flash("Пароль успешно изменен.", "success")
        return redirect(url_for("dashboard"))
    
    return render_template("change_password.html")


if __name__ == "__main__":
    # Инициализация БД и создание дефолтного админа при старте приложения
    with app.app_context():
        setup()
    app.run(debug=True)