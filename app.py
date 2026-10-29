import os
from functools import wraps
from datetime import datetime
from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, session, g
)
from werkzeug.security import generate_password_hash, check_password_hash
from config import Config
from database import get_db_connection, init_db

app = Flask(__name__)
app.config.from_object(Config)

# Ensure database tables exist
init_db()

# ==========================================
# Helpers & Context Processors
# ==========================================

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('user_id'):
            flash('يرجى تسجيل الدخول أولاً للوصول إلى هذه الصفحة.', 'warning')
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('user_id'):
            flash('يرجى تسجيل الدخول أولاً.', 'warning')
            return redirect(url_for('login', next=request.url))
        if session.get('user_role') != 'admin':
            flash('عذراً، هذه الصفحة مخصصة لمدير المنصة فقط.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

@app.context_processor
def inject_user_data():
    wallet_balance = 0.0
    if session.get('user_id'):
        conn = get_db_connection()
        user = conn.execute("SELECT wallet_balance, is_active FROM users WHERE id = ?", (session['user_id'],)).fetchone()
        conn.close()
        if user:
            wallet_balance = user['wallet_balance']
    return dict(current_user_wallet=wallet_balance)

# ==========================================
# Public & Auth Routes
# ==========================================

@app.route('/')
def index():
    conn = get_db_connection()
    courses = conn.execute("SELECT * FROM courses WHERE is_published = 1 ORDER BY id DESC LIMIT 6").fetchall()
    conn.close()
    return render_template('index.html', courses=courses)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('user_id'):
        if session.get('user_role') == 'admin':
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('student_dashboard'))

    if request.method == 'POST':
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '').strip()

        if not phone or not password:
            flash('يرجى إدخال رقم الهاتف وكلمة المرور.', 'danger')
            return render_template('login.html')

        conn = get_db_connection()
        user = conn.execute("SELECT * FROM users WHERE phone = ?", (phone,)).fetchone()
        conn.close()

        if user and check_password_hash(user['password_hash'], password):
            if not user['is_active']:
                flash('هذا الحساب تم تعطيله، يرجى التواصل مع الدعم الفني.', 'danger')
                return render_template('login.html')

            session['user_id'] = user['id']
            session['user_name'] = user['full_name']
            session['user_phone'] = user['phone']
            session['user_role'] = user['role']

            flash(f'أهلاً بك مجدداً يا {user["full_name"]}!', 'success')
            next_url = request.args.get('next')
            if next_url:
                return redirect(next_url)
            if user['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('student_dashboard'))
        else:
            flash('رقم الهاتف أو كلمة المرور غير صحيحة، حاول مجدداً.', 'danger')

    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if session.get('user_id'):
        return redirect(url_for('student_dashboard'))

    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        phone = request.form.get('phone', '').strip()
        division = request.form.get('division', 'عامة')
        password = request.form.get('password', '').strip()

        if not full_name or not phone or not password:
            flash('يرجى ملء جميع الحقول المطلوبة.', 'danger')
            return render_template('register.html')

        conn = get_db_connection()
        existing = conn.execute("SELECT id FROM users WHERE phone = ?", (phone,)).fetchone()
        if existing:
            conn.close()
            flash('رقم الهاتف هذا مسجل بالفعل مسبقاً، يمكنك تسجيل الدخول مباشرة.', 'warning')
            return redirect(url_for('login'))

        # Create user with 100 EGP welcome bonus
        welcome_bonus = 100.0
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO users (full_name, phone, password_hash, role, division, wallet_balance)
            VALUES (?, ?, ?, 'student', ?, ?)
        ''', (full_name, phone, generate_password_hash(password), division, welcome_bonus))
        new_user_id = cursor.lastrowid

        # Record welcome bonus in wallet transactions
        cursor.execute('''
            INSERT INTO wallet_transactions (user_id, amount, transaction_type, payment_method, status, notes)
            VALUES (?, ?, 'admin_adjustment', 'رصيد ترحيبي', 'approved', 'مكافأة ترحيبية فورية عند إنشاء الحساب')
        ''', (new_user_id, welcome_bonus))

        conn.commit()
        conn.close()

        session['user_id'] = new_user_id
        session['user_name'] = full_name
        session['user_phone'] = phone
        session['user_role'] = 'student'

        flash('تم إنشاء حسابك بنجاح وتمت إضافة 100 ج.م رصيد ترحيبي بمحفظتك!', 'success')
        return redirect(url_for('student_dashboard'))

    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('تم تسجيل الخروج بنجاح.', 'info')
    return redirect(url_for('index'))

# ==========================================
# Student Dashboard
# ==========================================

@app.route('/student/dashboard')
@login_required
def student_dashboard():
    user_id = session['user_id']
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    # Get enrolled courses
    enrolled_courses = conn.execute('''
        SELECT c.*, e.enrolled_at 
        FROM courses c
        JOIN enrollments e ON c.id = e.course_id
        WHERE e.user_id = ? AND e.status = 'active'
        ORDER BY e.enrolled_at DESC
    ''', (user_id,)).fetchall()

    # Get exam attempts history
    attempts = conn.execute('''
        SELECT a.*, e.title as exam_title, e.passing_score
        FROM exam_attempts a
        JOIN exams e ON a.exam_id = e.id
        WHERE a.user_id = ?
        ORDER BY a.started_at DESC
    ''', (user_id,)).fetchall()

    # Count pending wallet top-up requests
    pending_topups = conn.execute('''
        SELECT COUNT(*) FROM wallet_transactions 
        WHERE user_id = ? AND transaction_type = 'topup_request' AND status = 'pending'
    ''', (user_id,)).fetchone()[0]

    conn.close()
    return render_template('dashboard.html', 
                           user=user, 
                           enrolled_courses=enrolled_courses, 
                           attempts=attempts,
                           pending_topups_count=pending_topups)

# ==========================================
# Courses & Lessons
# ==========================================

@app.route('/courses')
def courses_list():
    subject_filter = request.args.get('subject')
    conn = get_db_connection()
    
    # Get subjects list
    subjects_rows = conn.execute("SELECT DISTINCT subject FROM courses WHERE is_published = 1").fetchall()
    subjects = [row['subject'] for row in subjects_rows]

    if subject_filter:
        courses = conn.execute('''
            SELECT c.*, (SELECT COUNT(*) FROM lessons WHERE course_id = c.id) as lessons_count
            FROM courses c
            WHERE c.is_published = 1 AND c.subject = ?
            ORDER BY c.id DESC
        ''', (subject_filter,)).fetchall()
    else:
        courses = conn.execute('''
            SELECT c.*, (SELECT COUNT(*) FROM lessons WHERE course_id = c.id) as lessons_count
            FROM courses c
            WHERE c.is_published = 1
            ORDER BY c.id DESC
        ''',).fetchall()

    enrolled_ids = []
    if session.get('user_id'):
        enrolled_rows = conn.execute("SELECT course_id FROM enrollments WHERE user_id = ? AND status = 'active'", (session['user_id'],)).fetchall()
        enrolled_ids = [r['course_id'] for r in enrolled_rows]

    conn.close()
    return render_template('courses.html', courses=courses, subjects=subjects, selected_subject=subject_filter, enrolled_ids=enrolled_ids)

@app.route('/courses/<int:course_id>')
def course_detail(course_id):
    conn = get_db_connection()
    course = conn.execute("SELECT * FROM courses WHERE id = ?", (course_id,)).fetchone()
    if not course:
        conn.close()
        flash('الكورس المطلوب غير موجود.', 'danger')
        return redirect(url_for('courses_list'))

    lessons = conn.execute("SELECT * FROM lessons WHERE course_id = ? ORDER BY lesson_order ASC", (course_id,)).fetchall()
    exams = conn.execute("SELECT * FROM exams WHERE course_id = ? AND is_published = 1 ORDER BY id DESC", (course_id,)).fetchall()

    is_enrolled = False
    if session.get('user_id'):
        if session.get('user_role') == 'admin':
            is_enrolled = True
        else:
            enrollment = conn.execute("SELECT id FROM enrollments WHERE user_id = ? AND course_id = ? AND status = 'active'", (session['user_id'], course_id)).fetchone()
            if enrollment:
                is_enrolled = True

    conn.close()
    return render_template('course_detail.html', course=course, lessons=lessons, exams=exams, is_enrolled=is_enrolled)

@app.route('/courses/<int:course_id>/enroll', methods=['POST'])
@login_required
def enroll_course(course_id):
    user_id = session['user_id']
    conn = get_db_connection()
    course = conn.execute("SELECT * FROM courses WHERE id = ?", (course_id,)).fetchone()
    if not course:
        conn.close()
        flash('الكورس غير موجود.', 'danger')
        return redirect(url_for('courses_list'))

    # Check if already enrolled
    existing = conn.execute("SELECT id FROM enrollments WHERE user_id = ? AND course_id = ? AND status = 'active'", (user_id, course_id)).fetchone()
    if existing:
        conn.close()
        flash('أنت مشترك بالفعل في هذا الكورس!', 'info')
        return redirect(url_for('course_detail', course_id=course_id))

    user = conn.execute("SELECT wallet_balance FROM users WHERE id = ?", (user_id,)).fetchone()
    price = course['price']

    if price > 0:
        if user['wallet_balance'] < price:
            conn.close()
            flash('عفواً، رصيد محفظتك لا يكفي لشراء هذا الكورس. يرجى شحن المحفظة أولاً.', 'danger')
            return redirect(url_for('wallet_view'))

        # Deduct wallet balance
        new_balance = user['wallet_balance'] - price
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET wallet_balance = ? WHERE id = ?", (new_balance, user_id))

        # Record transaction
        cursor.execute('''
            INSERT INTO wallet_transactions (user_id, amount, transaction_type, status, notes)
            VALUES (?, ?, 'course_purchase', 'approved', ?)
        ''', (user_id, price, f'شراء اشتراك كورس: {course["title"]}'))

    # Create enrollment
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO enrollments (user_id, course_id, status)
        VALUES (?, ?, 'active')
    ''', (user_id, course_id))

    conn.commit()
    conn.close()

    flash(f'تهانينا! تم تفعيل اشتراكك بنجاح في كورس: {course["title"]}.', 'success')
    return redirect(url_for('course_detail', course_id=course_id))

@app.route('/courses/<int:course_id>/transfer-payment', methods=['POST'])
@login_required
def transfer_payment_course(course_id):
    user_id = session['user_id']
    sender_phone = request.form.get('sender_phone', '').strip()
    reference_number = request.form.get('reference_number', '').strip()
    payment_method = request.form.get('payment_method', 'محفظة كاش').strip()
    
    if not sender_phone:
        flash('يرجى كتابة رقم الهاتف الذي قمت بالتحويل منه.', 'danger')
        return redirect(url_for('course_detail', course_id=course_id))

    conn = get_db_connection()
    course = conn.execute("SELECT * FROM courses WHERE id = ?", (course_id,)).fetchone()
    if not course:
        conn.close()
        flash('الكورس غير موجود.', 'danger')
        return redirect(url_for('courses_list'))

    price = course['price']
    cursor = conn.cursor()
    ref_text = f"محول من: {sender_phone}"
    if reference_number:
        ref_text += f" | مرجع: {reference_number}"

    cursor.execute('''
        INSERT INTO wallet_transactions (user_id, amount, transaction_type, payment_method, reference_number, status, notes)
        VALUES (?, ?, 'topup_request', ?, ?, 'pending', ?)
    ''', (user_id, price, payment_method, ref_text, f"طلب تفعيل كورس (id:{course_id}): {course['title']}"))
    
    conn.commit()
    conn.close()

    flash(f'تم استلام بيانات تحويلك لمبلغ {price:.2f} ج.م على الرقم 01279790505 بنجاح! جاري مراجعة التحويل وتفعيل الكورس في حسابك.', 'success')
    return redirect(url_for('course_detail', course_id=course_id))

@app.route('/lessons/<int:lesson_id>')
@login_required
def lesson_view(lesson_id):
    user_id = session['user_id']
    conn = get_db_connection()
    lesson = conn.execute("SELECT * FROM lessons WHERE id = ?", (lesson_id,)).fetchone()
    if not lesson:
        conn.close()
        flash('الدرس غير موجود.', 'danger')
        return redirect(url_for('courses_list'))

    course = conn.execute("SELECT * FROM courses WHERE id = ?", (lesson['course_id'],)).fetchone()
    
    # Check access permission
    has_access = False
    if session.get('user_role') == 'admin' or lesson['is_free_preview']:
        has_access = True
    else:
        enrollment = conn.execute("SELECT id FROM enrollments WHERE user_id = ? AND course_id = ? AND status = 'active'", (user_id, course['id'])).fetchone()
        if enrollment:
            has_access = True

    if not has_access:
        conn.close()
        flash('هذا الدرس متاح فقط للمشتركين في الكورس. يرجى الاشتراك للوصول إليه.', 'warning')
        return redirect(url_for('course_detail', course_id=course['id']))

    all_lessons = conn.execute("SELECT * FROM lessons WHERE course_id = ? ORDER BY lesson_order ASC", (course['id'],)).fetchall()
    
    # Identify Prev / Next
    prev_lesson = None
    next_lesson = None
    for idx, l in enumerate(all_lessons):
        if l['id'] == lesson_id:
            if idx > 0:
                prev_lesson = all_lessons[idx - 1]
            if idx < len(all_lessons) - 1:
                next_lesson = all_lessons[idx + 1]
            break

    conn.close()
    return render_template('lesson.html', lesson=lesson, course=course, all_lessons=all_lessons, prev_lesson=prev_lesson, next_lesson=next_lesson)

# ==========================================
# Online Examination System
# ==========================================

@app.route('/exams')
def exams_list():
    conn = get_db_connection()
    exams_query = '''
        SELECT e.*, c.title as course_title,
               (SELECT COUNT(*) FROM questions WHERE exam_id = e.id) as question_count
        FROM exams e
        LEFT JOIN courses c ON e.course_id = c.id
        WHERE e.is_published = 1
        ORDER BY e.id DESC
    '''
    exams = conn.execute(exams_query).fetchall()

    # Attach student's latest percentage if logged in
    exams_data = []
    for exam in exams:
        d = dict(exam)
        d['latest_percentage'] = None
        if session.get('user_id'):
            attempt = conn.execute('''
                SELECT percentage FROM exam_attempts 
                WHERE exam_id = ? AND user_id = ? 
                ORDER BY id DESC LIMIT 1
            ''', (exam['id'], session['user_id'])).fetchone()
            if attempt:
                d['latest_percentage'] = attempt['percentage']
        exams_data.append(d)

    conn.close()
    return render_template('exams.html', exams=exams_data)

@app.route('/exams/<int:exam_id>/take')
@login_required
def exam_take(exam_id):
    conn = get_db_connection()
    exam = conn.execute("SELECT * FROM exams WHERE id = ?", (exam_id,)).fetchone()
    if not exam or not exam['is_published']:
        conn.close()
        flash('هذا الاختبار غير متاح حالياً.', 'danger')
        return redirect(url_for('exams_list'))

    questions = conn.execute("SELECT * FROM questions WHERE exam_id = ? ORDER BY id ASC", (exam_id,)).fetchall()
    conn.close()

    if not questions:
        flash('لم تتم إضافة أسئلة لهذا الاختبار بعد.', 'warning')
        return redirect(url_for('exams_list'))

    return render_template('exam_take.html', exam=exam, questions=questions)

@app.route('/exams/<int:exam_id>/submit', methods=['POST'])
@login_required
def exam_submit(exam_id):
    user_id = session['user_id']
    conn = get_db_connection()
    exam = conn.execute("SELECT * FROM exams WHERE id = ?", (exam_id,)).fetchone()
    if not exam:
        conn.close()
        flash('الاختبار غير موجود.', 'danger')
        return redirect(url_for('exams_list'))

    questions = conn.execute("SELECT * FROM questions WHERE exam_id = ?", (exam_id,)).fetchall()
    
    total_points = 0
    student_score = 0
    answers_to_record = []

    for q in questions:
        q_id = q['id']
        points = q['points']
        correct_ans = q['correct_answer'].strip().upper()
        total_points += points

        chosen_ans = request.form.get(f'q_{q_id}', '').strip().upper()
        is_correct = 1 if (chosen_ans and chosen_ans == correct_ans) else 0
        points_awarded = points if is_correct else 0
        student_score += points_awarded

        answers_to_record.append({
            'question_id': q_id,
            'chosen_answer': chosen_ans,
            'is_correct': is_correct,
            'points_awarded': points_awarded
        })

    percentage = (student_score / total_points * 100) if total_points > 0 else 0
    passed = 1 if percentage >= exam['passing_score'] else 0

    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO exam_attempts (exam_id, user_id, score, total_points, percentage, passed, completed_at)
        VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
    ''', (exam_id, user_id, student_score, total_points, percentage, passed))
    attempt_id = cursor.lastrowid

    for ans in answers_to_record:
        cursor.execute('''
            INSERT INTO exam_answers (attempt_id, question_id, chosen_answer, is_correct, points_awarded)
            VALUES (?, ?, ?, ?, ?)
        ''', (attempt_id, ans['question_id'], ans['chosen_answer'], ans['is_correct'], ans['points_awarded']))

    conn.commit()
    conn.close()

    flash('تم تصحيح اختبارك وإظهار النتيجة فوراً!', 'success')
    return redirect(url_for('exam_result', attempt_id=attempt_id))

@app.route('/exams/results/<int:attempt_id>')
@login_required
def exam_result(attempt_id):
    user_id = session['user_id']
    conn = get_db_connection()
    attempt = conn.execute('''
        SELECT a.*, e.title as exam_title, e.passing_score
        FROM exam_attempts a
        JOIN exams e ON a.exam_id = e.id
        WHERE a.id = ?
    ''', (attempt_id,)).fetchone()

    if not attempt:
        conn.close()
        flash('نتيجة الاختبار غير موجودة.', 'danger')
        return redirect(url_for('exams_list'))

    # Security check: only student who took the exam or admin can view
    if attempt['user_id'] != user_id and session.get('user_role') != 'admin':
        conn.close()
        flash('غير مسموح بالاطلاع على نتيجة طالب آخر.', 'danger')
        return redirect(url_for('student_dashboard'))

    # Fetch detailed answers with questions
    answers_query = '''
        SELECT ea.*, q.question_text, q.question_type, q.option_a, q.option_b, 
               q.option_c, q.option_d, q.correct_answer, q.explanation, q.points
        FROM exam_answers ea
        JOIN questions q ON ea.question_id = q.id
        WHERE ea.attempt_id = ?
        ORDER BY ea.id ASC
    '''
    raw_answers = conn.execute(answers_query, (attempt_id,)).fetchall()
    
    # Map letter to option text for readable display
    def get_opt_text(row, code):
        if not code:
            return None
        code = code.upper()
        if code == 'A': return f"(أ) {row['option_a']}"
        if code == 'B': return f"(ب) {row['option_b']}"
        if code == 'C': return f"(ج) {row['option_c'] or ''}"
        if code == 'D': return f"(د) {row['option_d'] or ''}"
        return code

    processed_answers = []
    for row in raw_answers:
        d = dict(row)
        d['chosen_text'] = get_opt_text(row, row['chosen_answer'])
        d['correct_text'] = get_opt_text(row, row['correct_answer'])
        processed_answers.append(d)

    conn.close()
    return render_template('exam_result.html', attempt=attempt, answers=processed_answers)

# ==========================================
# Wallet Management
# ==========================================

@app.route('/wallet')
@login_required
def wallet_view():
    user_id = session['user_id']
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    transactions = conn.execute('''
        SELECT * FROM wallet_transactions 
        WHERE user_id = ? 
        ORDER BY id DESC
    ''', (user_id,)).fetchall()
    conn.close()
    return render_template('wallet.html', user=user, transactions=transactions)

@app.route('/wallet/topup', methods=['POST'])
@login_required
def wallet_topup_request():
    user_id = session['user_id']
    amount = float(request.form.get('amount', 0))
    payment_method = request.form.get('payment_method', '').strip()
    reference_number = request.form.get('reference_number', '').strip()
    notes = request.form.get('notes', '').strip()

    if amount <= 0 or not reference_number:
        flash('يرجى إدخال مبلغ صحيح ورقم التحويل / العملية.', 'danger')
        return redirect(url_for('wallet_view'))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO wallet_transactions (user_id, amount, transaction_type, payment_method, reference_number, status, notes)
        VALUES (?, ?, 'topup_request', ?, ?, 'pending', ?)
    ''', (user_id, amount, payment_method, reference_number, notes))
    conn.commit()
    conn.close()

    flash('تم تسجيل طلب الشحن بنجاح! سيتم مراجعته وتأكيد إضافة الرصيد إلى محفظتك في أقرب وقت.', 'success')
    return redirect(url_for('wallet_view'))

# ==========================================
# Discussion Forum
# ==========================================

@app.route('/forum')
def forum_index():
    subject_filter = request.args.get('subject')
    conn = get_db_connection()
    
    subjects_rows = conn.execute("SELECT DISTINCT subject FROM forum_posts").fetchall()
    subjects = [r['subject'] for r in subjects_rows]
    for default_subj in ['اللغة العربية', 'اللغة الإنجليزية', 'التاريخ', 'الفيزياء', 'الكيمياء']:
        if default_subj not in subjects:
            subjects.append(default_subj)

    if subject_filter:
        posts = conn.execute('''
            SELECT p.*, u.full_name as author_name, u.role as author_role,
                   (SELECT COUNT(*) FROM forum_replies WHERE post_id = p.id) as reply_count
            FROM forum_posts p
            JOIN users u ON p.user_id = u.id
            WHERE p.subject = ?
            ORDER BY p.id DESC
        ''', (subject_filter,)).fetchall()
    else:
        posts = conn.execute('''
            SELECT p.*, u.full_name as author_name, u.role as author_role,
                   (SELECT COUNT(*) FROM forum_replies WHERE post_id = p.id) as reply_count
            FROM forum_posts p
            JOIN users u ON p.user_id = u.id
            ORDER BY p.id DESC
        ''').fetchall()

    conn.close()
    return render_template('forum.html', posts=posts, subjects=subjects, selected_subject=subject_filter)

@app.route('/forum/posts/<int:post_id>')
def forum_post_view(post_id):
    conn = get_db_connection()
    post = conn.execute('''
        SELECT p.*, u.full_name as author_name, u.role as author_role
        FROM forum_posts p
        JOIN users u ON p.user_id = u.id
        WHERE p.id = ?
    ''', (post_id,)).fetchone()

    if not post:
        conn.close()
        flash('الموضوع غير موجود.', 'danger')
        return redirect(url_for('forum_index'))

    replies = conn.execute('''
        SELECT r.*, u.full_name as author_name, u.role as author_role
        FROM forum_replies r
        JOIN users u ON r.user_id = u.id
        WHERE r.post_id = ?
        ORDER BY r.id ASC
    ''', (post_id,)).fetchall()

    conn.close()
    return render_template('forum_post.html', post=post, replies=replies)

@app.route('/forum/posts/create', methods=['POST'])
@login_required
def forum_create_post():
    user_id = session['user_id']
    subject = request.form.get('subject', '').strip()
    title = request.form.get('title', '').strip()
    content = request.form.get('content', '').strip()

    if not title or not content:
        flash('يرجى كتابة عنوان ونص السؤال.', 'danger')
        return redirect(url_for('forum_index'))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO forum_posts (user_id, subject, title, content)
        VALUES (?, ?, ?, ?)
    ''', (user_id, subject, title, content))
    conn.commit()
    post_id = cursor.lastrowid
    conn.close()

    flash('تم نشر سؤالك بنجاح في منتدى المنصة!', 'success')
    return redirect(url_for('forum_post_view', post_id=post_id))

@app.route('/forum/posts/<int:post_id>/reply', methods=['POST'])
@login_required
def forum_reply(post_id):
    user_id = session['user_id']
    content = request.form.get('content', '').strip()

    if not content:
        flash('لا يمكن إرسال رد فارغ.', 'warning')
        return redirect(url_for('forum_post_view', post_id=post_id))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO forum_replies (post_id, user_id, content)
        VALUES (?, ?, ?)
    ''', (post_id, user_id, content))
    conn.commit()
    conn.close()

    flash('تمت إضافة ردك بنجاح.', 'success')
    return redirect(url_for('forum_post_view', post_id=post_id))

# ==========================================
# Administrative Dashboard & Routes
# ==========================================

@app.route('/admin')
@admin_required
def admin_dashboard():
    conn = get_db_connection()
    
    stats = {
        'students_count': conn.execute("SELECT COUNT(*) FROM users WHERE role = 'student'").fetchone()[0],
        'courses_count': conn.execute("SELECT COUNT(*) FROM courses").fetchone()[0],
        'exams_count': conn.execute("SELECT COUNT(*) FROM exams").fetchone()[0],
    }

    pending_requests = conn.execute('''
        SELECT t.*, u.full_name, u.phone
        FROM wallet_transactions t
        JOIN users u ON t.user_id = u.id
        WHERE t.transaction_type = 'topup_request' AND t.status = 'pending'
        ORDER BY t.id DESC
        LIMIT 10
    ''').fetchall()

    pending_topups_count = len(pending_requests)
    conn.close()

    return render_template('admin/dashboard.html', 
                           stats=stats, 
                           pending_requests=pending_requests,
                           pending_topups_count=pending_topups_count)

# Admin: Courses
@app.route('/admin/courses')
@admin_required
def admin_courses():
    conn = get_db_connection()
    courses = conn.execute('''
        SELECT c.*, (SELECT COUNT(*) FROM lessons WHERE course_id = c.id) as lessons_count
        FROM courses c
        ORDER BY c.id DESC
    ''').fetchall()
    conn.close()
    return render_template('admin/courses.html', courses=courses)

@app.route('/admin/courses/create', methods=['GET', 'POST'])
@admin_required
def admin_course_create():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        subject = request.form.get('subject', '').strip()
        grade = request.form.get('grade', 'الصف الثالث الثانوي (بكالوريا)').strip()
        price = float(request.form.get('price', 0))
        image_url = request.form.get('image_url', '').strip()
        description = request.form.get('description', '').strip()
        is_published = 1 if request.form.get('is_published') else 0

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO courses (title, subject, grade, price, image_url, description, is_published)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (title, subject, grade, price, image_url, description, is_published))
        conn.commit()
        conn.close()

        flash('تمت إضافة الكورس بنجاح.', 'success')
        return redirect(url_for('admin_courses'))

    return render_template('admin/course_form.html', course=None)

@app.route('/admin/courses/<int:course_id>/edit', methods=['GET', 'POST'])
@admin_required
def admin_course_edit(course_id):
    conn = get_db_connection()
    course = conn.execute("SELECT * FROM courses WHERE id = ?", (course_id,)).fetchone()
    if not course:
        conn.close()
        flash('الكورس غير موجود.', 'danger')
        return redirect(url_for('admin_courses'))

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        subject = request.form.get('subject', '').strip()
        grade = request.form.get('grade', '').strip()
        price = float(request.form.get('price', 0))
        image_url = request.form.get('image_url', '').strip()
        description = request.form.get('description', '').strip()
        is_published = 1 if request.form.get('is_published') else 0

        cursor = conn.cursor()
        cursor.execute('''
            UPDATE courses 
            SET title = ?, subject = ?, grade = ?, price = ?, image_url = ?, description = ?, is_published = ?
            WHERE id = ?
        ''', (title, subject, grade, price, image_url, description, is_published, course_id))
        conn.commit()
        conn.close()

        flash('تم تحديث بيانات الكورس بنجاح.', 'success')
        return redirect(url_for('admin_courses'))

    conn.close()
    return render_template('admin/course_form.html', course=course)

@app.route('/admin/courses/<int:course_id>/delete', methods=['POST'])
@admin_required
def admin_course_delete(course_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM courses WHERE id = ?", (course_id,))
    conn.commit()
    conn.close()
    flash('تم حذف الكورس بنجاح.', 'info')
    return redirect(url_for('admin_courses'))

# Admin: Lessons
@app.route('/admin/courses/<int:course_id>/lessons')
@admin_required
def admin_course_lessons(course_id):
    conn = get_db_connection()
    course = conn.execute("SELECT * FROM courses WHERE id = ?", (course_id,)).fetchone()
    lessons = conn.execute("SELECT * FROM lessons WHERE course_id = ? ORDER BY lesson_order ASC", (course_id,)).fetchall()
    conn.close()
    return render_template('admin/lessons.html', course=course, lessons=lessons)

@app.route('/admin/courses/<int:course_id>/lessons/create', methods=['GET', 'POST'])
@admin_required
def admin_lesson_create(course_id):
    conn = get_db_connection()
    course = conn.execute("SELECT * FROM courses WHERE id = ?", (course_id,)).fetchone()
    last_order = conn.execute("SELECT MAX(lesson_order) FROM lessons WHERE course_id = ?", (course_id,)).fetchone()[0]
    next_order = (last_order or 0) + 1

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        lesson_order = int(request.form.get('lesson_order', next_order))
        pdf_url = request.form.get('pdf_url', '').strip()
        video_url = request.form.get('video_url', '').strip()
        description = request.form.get('description', '').strip()
        is_free_preview = 1 if request.form.get('is_free_preview') else 0

        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO lessons (course_id, title, lesson_order, pdf_url, video_url, description, is_free_preview)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (course_id, title, lesson_order, pdf_url, video_url, description, is_free_preview))
        conn.commit()
        conn.close()

        flash('تمت إضافة الدرس بنجاح للكورس.', 'success')
        return redirect(url_for('admin_course_lessons', course_id=course_id))

    conn.close()
    return render_template('admin/lesson_form.html', course=course, lesson=None, next_order=next_order)

@app.route('/admin/lessons/<int:lesson_id>/edit', methods=['GET', 'POST'])
@admin_required
def admin_lesson_edit(lesson_id):
    conn = get_db_connection()
    lesson = conn.execute("SELECT * FROM lessons WHERE id = ?", (lesson_id,)).fetchone()
    if not lesson:
        conn.close()
        flash('الدرس غير موجود.', 'danger')
        return redirect(url_for('admin_courses'))

    course = conn.execute("SELECT * FROM courses WHERE id = ?", (lesson['course_id'],)).fetchone()

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        lesson_order = int(request.form.get('lesson_order', 1))
        pdf_url = request.form.get('pdf_url', '').strip()
        video_url = request.form.get('video_url', '').strip()
        description = request.form.get('description', '').strip()
        is_free_preview = 1 if request.form.get('is_free_preview') else 0

        cursor = conn.cursor()
        cursor.execute('''
            UPDATE lessons 
            SET title = ?, lesson_order = ?, pdf_url = ?, video_url = ?, description = ?, is_free_preview = ?
            WHERE id = ?
        ''', (title, lesson_order, pdf_url, video_url, description, is_free_preview, lesson_id))
        conn.commit()
        conn.close()

        flash('تم تحديث بيانات الدرس بنجاح.', 'success')
        return redirect(url_for('admin_course_lessons', course_id=course['id']))

    conn.close()
    return render_template('admin/lesson_form.html', course=course, lesson=lesson, next_order=None)

@app.route('/admin/lessons/<int:lesson_id>/delete', methods=['POST'])
@admin_required
def admin_lesson_delete(lesson_id):
    conn = get_db_connection()
    lesson = conn.execute("SELECT course_id FROM lessons WHERE id = ?", (lesson_id,)).fetchone()
    course_id = lesson['course_id'] if lesson else None
    
    cursor = conn.cursor()
    cursor.execute("DELETE FROM lessons WHERE id = ?", (lesson_id,))
    conn.commit()
    conn.close()

    flash('تم حذف الدرس بنجاح.', 'info')
    if course_id:
        return redirect(url_for('admin_course_lessons', course_id=course_id))
    return redirect(url_for('admin_courses'))

# Admin: Exams
@app.route('/admin/exams')
@admin_required
def admin_exams():
    conn = get_db_connection()
    exams = conn.execute('''
        SELECT e.*, c.title as course_title,
               (SELECT COUNT(*) FROM questions WHERE exam_id = e.id) as question_count
        FROM exams e
        LEFT JOIN courses c ON e.course_id = c.id
        ORDER BY e.id DESC
    ''').fetchall()
    conn.close()
    return render_template('admin/exams.html', exams=exams)

@app.route('/admin/exams/create', methods=['GET', 'POST'])
@admin_required
def admin_exam_create():
    conn = get_db_connection()
    courses = conn.execute("SELECT id, title, subject FROM courses ORDER BY id DESC").fetchall()

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        course_id_raw = request.form.get('course_id')
        course_id = int(course_id_raw) if course_id_raw else None
        duration_minutes = int(request.form.get('duration_minutes', 30))
        passing_score = int(request.form.get('passing_score', 50))
        description = request.form.get('description', '').strip()
        is_published = 1 if request.form.get('is_published') else 0

        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO exams (course_id, title, duration_minutes, passing_score, description, is_published)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (course_id, title, duration_minutes, passing_score, description, is_published))
        conn.commit()
        exam_id = cursor.lastrowid
        conn.close()

        flash('تم إنشاء الاختبار بنجاح، يمكنك الآن إضافة الأسئلة إليه.', 'success')
        return redirect(url_for('admin_exam_questions', exam_id=exam_id))

    conn.close()
    return render_template('admin/exam_form.html', exam=None, courses=courses)

@app.route('/admin/exams/<int:exam_id>/edit', methods=['GET', 'POST'])
@admin_required
def admin_exam_edit(exam_id):
    conn = get_db_connection()
    exam = conn.execute("SELECT * FROM exams WHERE id = ?", (exam_id,)).fetchone()
    courses = conn.execute("SELECT id, title, subject FROM courses ORDER BY id DESC").fetchall()

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        course_id_raw = request.form.get('course_id')
        course_id = int(course_id_raw) if course_id_raw else None
        duration_minutes = int(request.form.get('duration_minutes', 30))
        passing_score = int(request.form.get('passing_score', 50))
        description = request.form.get('description', '').strip()
        is_published = 1 if request.form.get('is_published') else 0

        cursor = conn.cursor()
        cursor.execute('''
            UPDATE exams 
            SET title = ?, course_id = ?, duration_minutes = ?, passing_score = ?, description = ?, is_published = ?
            WHERE id = ?
        ''', (title, course_id, duration_minutes, passing_score, description, is_published, exam_id))
        conn.commit()
        conn.close()

        flash('تم تحديث بيانات الاختبار بنجاح.', 'success')
        return redirect(url_for('admin_exams'))

    conn.close()
    return render_template('admin/exam_form.html', exam=exam, courses=courses)

@app.route('/admin/exams/<int:exam_id>/delete', methods=['POST'])
@admin_required
def admin_exam_delete(exam_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM exams WHERE id = ?", (exam_id,))
    conn.commit()
    conn.close()
    flash('تم حذف الاختبار بنجاح.', 'info')
    return redirect(url_for('admin_exams'))

# Admin: Questions
@app.route('/admin/exams/<int:exam_id>/questions')
@admin_required
def admin_exam_questions(exam_id):
    conn = get_db_connection()
    exam = conn.execute("SELECT * FROM exams WHERE id = ?", (exam_id,)).fetchone()
    questions = conn.execute("SELECT * FROM questions WHERE exam_id = ? ORDER BY id ASC", (exam_id,)).fetchall()
    conn.close()
    return render_template('admin/questions.html', exam=exam, questions=questions)

@app.route('/admin/exams/<int:exam_id>/questions/create', methods=['GET', 'POST'])
@admin_required
def admin_question_create(exam_id):
    conn = get_db_connection()
    exam = conn.execute("SELECT * FROM exams WHERE id = ?", (exam_id,)).fetchone()

    if request.method == 'POST':
        question_text = request.form.get('question_text', '').strip()
        question_type = request.form.get('question_type', 'mcq')
        question_image = request.form.get('question_image', '').strip()
        option_a = request.form.get('option_a', '').strip()
        option_b = request.form.get('option_b', '').strip()
        option_c = request.form.get('option_c', '').strip() if question_type == 'mcq' else None
        option_d = request.form.get('option_d', '').strip() if question_type == 'mcq' else None
        correct_answer = request.form.get('correct_answer', 'A').strip().upper()
        explanation = request.form.get('explanation', '').strip()
        points = int(request.form.get('points', 1))

        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO questions (exam_id, question_text, question_image, question_type, option_a, option_b, option_c, option_d, correct_answer, explanation, points)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (exam_id, question_text, question_image, question_type, option_a, option_b, option_c, option_d, correct_answer, explanation, points))
        conn.commit()
        conn.close()

        flash('تمت إضافة السؤال بنجاح للاختبار.', 'success')
        return redirect(url_for('admin_exam_questions', exam_id=exam_id))

    conn.close()
    return render_template('admin/question_form.html', exam=exam, question=None)

@app.route('/admin/questions/<int:question_id>/edit', methods=['GET', 'POST'])
@admin_required
def admin_question_edit(question_id):
    conn = get_db_connection()
    question = conn.execute("SELECT * FROM questions WHERE id = ?", (question_id,)).fetchone()
    if not question:
        conn.close()
        flash('السؤال غير موجود.', 'danger')
        return redirect(url_for('admin_exams'))

    exam = conn.execute("SELECT * FROM exams WHERE id = ?", (question['exam_id'],)).fetchone()

    if request.method == 'POST':
        question_text = request.form.get('question_text', '').strip()
        question_type = request.form.get('question_type', 'mcq')
        question_image = request.form.get('question_image', '').strip()
        option_a = request.form.get('option_a', '').strip()
        option_b = request.form.get('option_b', '').strip()
        option_c = request.form.get('option_c', '').strip() if question_type == 'mcq' else None
        option_d = request.form.get('option_d', '').strip() if question_type == 'mcq' else None
        correct_answer = request.form.get('correct_answer', 'A').strip().upper()
        explanation = request.form.get('explanation', '').strip()
        points = int(request.form.get('points', 1))

        cursor = conn.cursor()
        cursor.execute('''
            UPDATE questions 
            SET question_text = ?, question_image = ?, question_type = ?, option_a = ?, option_b = ?,
                option_c = ?, option_d = ?, correct_answer = ?, explanation = ?, points = ?
            WHERE id = ?
        ''', (question_text, question_image, question_type, option_a, option_b, option_c, option_d, correct_answer, explanation, points, question_id))
        conn.commit()
        conn.close()

        flash('تم تحديث السؤال بنجاح.', 'success')
        return redirect(url_for('admin_exam_questions', exam_id=exam['id']))

    conn.close()
    return render_template('admin/question_form.html', exam=exam, question=question)

@app.route('/admin/questions/<int:question_id>/delete', methods=['POST'])
@admin_required
def admin_question_delete(question_id):
    conn = get_db_connection()
    q = conn.execute("SELECT exam_id FROM questions WHERE id = ?", (question_id,)).fetchone()
    exam_id = q['exam_id'] if q else None

    cursor = conn.cursor()
    cursor.execute("DELETE FROM questions WHERE id = ?", (question_id,))
    conn.commit()
    conn.close()

    flash('تم حذف السؤال بنجاح.', 'info')
    if exam_id:
        return redirect(url_for('admin_exam_questions', exam_id=exam_id))
    return redirect(url_for('admin_exams'))

# Admin: Wallet Top-Up Requests
@app.route('/admin/wallet/requests')
@admin_required
def admin_wallet_requests():
    filter_status = request.args.get('status')
    conn = get_db_connection()

    all_count = conn.execute("SELECT COUNT(*) FROM wallet_transactions WHERE transaction_type = 'topup_request'").fetchone()[0]
    pending_count = conn.execute("SELECT COUNT(*) FROM wallet_transactions WHERE transaction_type = 'topup_request' AND status = 'pending'").fetchone()[0]

    if filter_status:
        query = '''
            SELECT t.*, u.full_name, u.phone
            FROM wallet_transactions t
            JOIN users u ON t.user_id = u.id
            WHERE t.transaction_type = 'topup_request' AND t.status = ?
            ORDER BY t.id DESC
        '''
        requests_list = conn.execute(query, (filter_status,)).fetchall()
    else:
        query = '''
            SELECT t.*, u.full_name, u.phone
            FROM wallet_transactions t
            JOIN users u ON t.user_id = u.id
            WHERE t.transaction_type = 'topup_request'
            ORDER BY t.id DESC
        '''
        requests_list = conn.execute(query).fetchall()

    conn.close()
    return render_template('admin/wallet_requests.html', 
                           requests=requests_list, 
                           filter_status=filter_status,
                           all_count=all_count,
                           pending_count=pending_count)

@app.route('/admin/wallet/requests/<int:tx_id>/action', methods=['POST'])
@admin_required
def admin_wallet_action(tx_id):
    action = request.form.get('action') # 'approve' or 'reject'
    conn = get_db_connection()
    tx = conn.execute("SELECT * FROM wallet_transactions WHERE id = ?", (tx_id,)).fetchone()
    if not tx or tx['status'] != 'pending':
        conn.close()
        flash('الطلب غير صالح أو تم اتخاذ إجراء بشأنه مسبقاً.', 'warning')
        return redirect(url_for('admin_wallet_requests'))

    cursor = conn.cursor()
    if action == 'approve':
        # Add to student balance
        cursor.execute("UPDATE users SET wallet_balance = wallet_balance + ? WHERE id = ?", (tx['amount'], tx['user_id']))
        cursor.execute("UPDATE wallet_transactions SET status = 'approved', updated_at = datetime('now') WHERE id = ?", (tx_id,))
        
        # Check if this was a direct course activation request
        notes = tx['notes'] or ''
        activated_course = False
        if '(id:' in notes:
            try:
                c_id = int(notes.split('(id:')[1].split(')')[0])
                cursor.execute("INSERT OR IGNORE INTO enrollments (user_id, course_id, status) VALUES (?, ?, 'active')", (tx['user_id'], c_id))
                activated_course = True
            except Exception:
                pass

        if activated_course:
            flash(f'تم اعتماد التحويل وتفعيل الكورس في حساب الطالب بنجاح!', 'success')
        else:
            flash(f'تم اعتماد طلب الشحن وإضافة {tx["amount"]} ج.م إلى رصيد الطالب بنجاح!', 'success')
    elif action == 'reject':
        cursor.execute("UPDATE wallet_transactions SET status = 'rejected', updated_at = datetime('now') WHERE id = ?", (tx_id,))
        flash('تم رفض طلب الشحن.', 'info')

    conn.commit()
    conn.close()
    return redirect(url_for('admin_wallet_requests'))

# Admin: Students
@app.route('/admin/students')
@admin_required
def admin_students():
    conn = get_db_connection()
    students = conn.execute("SELECT * FROM users WHERE role = 'student' ORDER BY id DESC").fetchall()
    conn.close()
    return render_template('admin/students.html', students=students)

@app.route('/admin/students/<int:student_id>/adjust-balance', methods=['POST'])
@admin_required
def admin_student_adjust_balance(student_id):
    new_balance = float(request.form.get('new_balance', 0))
    reason = request.form.get('reason', 'تعديل مباشر من إدارة المنصة').strip()

    conn = get_db_connection()
    student = conn.execute("SELECT * FROM users WHERE id = ?", (student_id,)).fetchone()
    if not student:
        conn.close()
        flash('الطالب غير موجود.', 'danger')
        return redirect(url_for('admin_students'))

    diff = new_balance - student['wallet_balance']
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET wallet_balance = ? WHERE id = ?", (new_balance, student_id))
    
    # Record transaction adjustment
    cursor.execute('''
        INSERT INTO wallet_transactions (user_id, amount, transaction_type, payment_method, status, notes)
        VALUES (?, ?, 'admin_adjustment', 'تعديل رصيد إداري', 'approved', ?)
    ''', (student_id, diff, reason))

    conn.commit()
    conn.close()

    flash(f'تم تعديل رصيد الطالب {student["full_name"]} إلى {new_balance:.2f} ج.م بنجاح.', 'success')
    return redirect(url_for('admin_students'))

@app.route('/admin/students/<int:student_id>/toggle-active', methods=['POST'])
@admin_required
def admin_student_toggle_active(student_id):
    conn = get_db_connection()
    student = conn.execute("SELECT is_active, full_name FROM users WHERE id = ?", (student_id,)).fetchone()
    if student:
        new_status = 0 if student['is_active'] else 1
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_active = ? WHERE id = ?", (new_status, student_id))
        conn.commit()
        status_text = 'تنشيط' if new_status else 'تعطيل'
        flash(f'تم {status_text} حساب الطالب {student["full_name"]}.', 'info')
    conn.close()
    return redirect(url_for('admin_students'))

# ==========================================
# Run application
# ==========================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
