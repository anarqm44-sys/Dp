import sqlite3
import os
from werkzeug.security import generate_password_hash
from config import Config

def get_db_connection():
    db_path = Config.DATABASE_PATH
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.executescript('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        full_name TEXT NOT NULL,
        phone TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT DEFAULT 'student',
        division TEXT DEFAULT 'عامة',
        wallet_balance REAL DEFAULT 0.0,
        is_active INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS courses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT,
        subject TEXT NOT NULL,
        grade TEXT DEFAULT 'الصف الثالث الثانوي (بكالوريا)',
        price REAL DEFAULT 0.0,
        image_url TEXT,
        is_published INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS lessons (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        course_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        description TEXT,
        video_url TEXT,
        pdf_url TEXT,
        lesson_order INTEGER DEFAULT 1,
        is_free_preview INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (course_id) REFERENCES courses (id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS enrollments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        course_id INTEGER NOT NULL,
        enrolled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        status TEXT DEFAULT 'active',
        UNIQUE(user_id, course_id),
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
        FOREIGN KEY (course_id) REFERENCES courses (id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS wallet_transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        amount REAL NOT NULL,
        transaction_type TEXT NOT NULL,
        payment_method TEXT,
        reference_number TEXT,
        status TEXT DEFAULT 'pending',
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS exams (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        course_id INTEGER,
        title TEXT NOT NULL,
        description TEXT,
        duration_minutes INTEGER DEFAULT 30,
        passing_score INTEGER DEFAULT 50,
        is_published INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (course_id) REFERENCES courses (id) ON DELETE SET NULL
    );

    CREATE TABLE IF NOT EXISTS questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        exam_id INTEGER NOT NULL,
        question_text TEXT NOT NULL,
        question_image TEXT,
        question_type TEXT DEFAULT 'mcq',
        option_a TEXT NOT NULL,
        option_b TEXT NOT NULL,
        option_c TEXT,
        option_d TEXT,
        correct_answer TEXT NOT NULL,
        explanation TEXT,
        points INTEGER DEFAULT 1,
        FOREIGN KEY (exam_id) REFERENCES exams (id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS exam_attempts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        exam_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        score REAL DEFAULT 0,
        total_points REAL DEFAULT 0,
        percentage REAL DEFAULT 0,
        passed INTEGER DEFAULT 0,
        started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        completed_at TIMESTAMP,
        FOREIGN KEY (exam_id) REFERENCES exams (id) ON DELETE CASCADE,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS exam_answers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        attempt_id INTEGER NOT NULL,
        question_id INTEGER NOT NULL,
        chosen_answer TEXT,
        is_correct INTEGER DEFAULT 0,
        points_awarded REAL DEFAULT 0,
        FOREIGN KEY (attempt_id) REFERENCES exam_attempts (id) ON DELETE CASCADE,
        FOREIGN KEY (question_id) REFERENCES questions (id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS forum_posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        course_id INTEGER,
        subject TEXT NOT NULL,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
        FOREIGN KEY (course_id) REFERENCES courses (id) ON DELETE SET NULL
    );

    CREATE TABLE IF NOT EXISTS forum_replies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        post_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        content TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (post_id) REFERENCES forum_posts (id) ON DELETE CASCADE,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
    );
    ''')

    # Seed Admin User if not exists
    admin = cursor.execute("SELECT * FROM users WHERE phone = ?", ('01000000000',)).fetchone()
    if not admin:
        cursor.execute('''
            INSERT INTO users (full_name, phone, password_hash, role, division, wallet_balance)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', ('مدير المنصة', '01000000000', generate_password_hash('admin123'), 'admin', 'إدارة عامة', 1000.0))

    # Seed demo student if not exists
    student = cursor.execute("SELECT * FROM users WHERE phone = ?", ('01111111111',)).fetchone()
    if not student:
        cursor.execute('''
            INSERT INTO users (full_name, phone, password_hash, role, division, wallet_balance)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', ('أحمد محمود محمد', '01111111111', generate_password_hash('student123'), 'student', 'علمي علوم', 250.0))

    # Seed initial courses if empty
    course_count = cursor.execute("SELECT COUNT(*) FROM courses").fetchone()[0]
    if course_count == 0:
        courses_data = [
            (
                'كورس اللغة العربية الشامل - النحو والبلاغة',
                'شرح تفصيلي ومبسط لجميع وحدات النحو وقواعد البلاغة للثانوية العامة مع تدريبات مكثفة ونماذج امتحانات وزارية سابقة.',
                'اللغة العربية',
                'الصف الثالث الثانوي',
                150.0,
                1
            ),
            (
                'كورس اللغة الإنجليزية المكثف - القواعد ومهارات الترجمة',
                'إتقان مهارات اللغة الإنجليزية وقواعد الثانوية العامة وحل أسئلة الفهم والقطع النثرية والتدريب على نمط الامتحانات الحديثة.',
                'اللغة الإنجليزية',
                'الصف الثالث الثانوي',
                120.0,
                1
            ),
            (
                'كورس التاريخ الشامل - المنهج الحديث والخرائط الذهنية',
                'دراسة تفاعلية لأحداث وفصول منهج التاريخ لطلاب الشعبة الأدبية مع تلخيصات ذكية وأسئلة استنتاجية متقدمة.',
                'التاريخ',
                'الصف الثالث الثانوي',
                100.0,
                1
            )
        ]
        cursor.executemany('''
            INSERT INTO courses (title, description, subject, grade, price, is_published)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', courses_data)

        # Retrieve course IDs
        arabic_id = cursor.execute("SELECT id FROM courses WHERE subject = 'اللغة العربية'").fetchone()[0]
        english_id = cursor.execute("SELECT id FROM courses WHERE subject = 'اللغة الإنجليزية'").fetchone()[0]
        history_id = cursor.execute("SELECT id FROM courses WHERE subject = 'التاريخ'").fetchone()[0]

        # Seed lessons
        lessons_data = [
            (
                arabic_id,
                'الوحدة الأولى: همزة الوصل والقطع والمشتقات العاملة',
                'شرح تفصيلي لقواعد الوحدة الأولى مع حل أكثر من 50 سؤال تدريبي.',
                'https://www.youtube.com/embed/dQw4w9WgXcQ',
                'https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf',
                1,
                1
            ),
            (
                arabic_id,
                'الوحدة الثانية: المصادر وأنواعها وأحكام اسم الفاعل',
                'شرح صياغة المصادر الثلاثية وغير الثلاثية وإعمال اسم الفاعل.',
                'https://www.youtube.com/embed/dQw4w9WgXcQ',
                'https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf',
                2,
                0
            ),
            (
                english_id,
                'Unit 1: Past Tenses & Narrative Style',
                'Review of Past Simple, Past Continuous and Past Perfect with exam questions.',
                'https://www.youtube.com/embed/dQw4w9WgXcQ',
                'https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf',
                1,
                1
            )
        ]
        cursor.executemany('''
            INSERT INTO lessons (course_id, title, description, video_url, pdf_url, lesson_order, is_free_preview)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', lessons_data)

        # Seed initial Exam
        cursor.execute('''
            INSERT INTO exams (course_id, title, description, duration_minutes, passing_score, is_published)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            arabic_id,
            'اختبار الوحدة الأولى في النحو والإملاء',
            'اختبار شامل يقيس استيعاب قواعد همزة القطع والوصل والمشتقات مع تصحيح فوري وشرح تفصيلي للإجابات.',
            20,
            60,
            1
        ))
        exam_id = cursor.lastrowid

        # Seed questions
        questions_data = [
            (
                exam_id,
                'ما حكم همزة كلمة (استغفار) وما سببها؟',
                'mcq',
                'همزة قطع لأنها مصدر رباعي',
                'همزة وصل لأنها مصدر سداسي',
                'همزة قطع لأنها فعل ماضٍ',
                'همزة وصل لأنها اسم من الأسماء التسعة',
                'B',
                'كلمة (استغفار) مصدر للفعل السداسي (استغفر)، ومصادر الأفعال السداسية همزتها همزة وصل دائماً.',
                2
            ),
            (
                exam_id,
                'أي الجمل الآتية تشتمل على اسم فاعل عامل عمل فعله؟',
                'mcq',
                'حضر المهندس إلى المصنع باكراً',
                'المعلم شارحٌ الدرسَ بإتقان',
                'هذا القاضي يحكم بالعدل',
                'سافر الطالب إلى الجامعة',
                'B',
                'في جملة (المعلم شارحٌ الدرسَ) جاء اسم الفاعل (شارحٌ) نكرة منونة معتمدة على مبتدأ ودلت على الحال والاستقبال ونصب مفعولاً به (الدرسَ).',
                2
            ),
            (
                exam_id,
                'كلمة (امرؤ) تكتب بالواو في حالة الرفع وبالألف في حالة النصب وبالياء في حالة الجر.',
                'true_false',
                'صح',
                'خطأ',
                None,
                None,
                'A',
                'صحيح، كلمة امرؤ تتغير حركة همزتها المتطرفة بحسب موقعها الإعرابي: امرؤ (رفعاً)، امرأً (نصباً)، امرئٍ (جراً).',
                1
            )
        ]
        cursor.executemany('''
            INSERT INTO questions (exam_id, question_text, question_type, option_a, option_b, option_c, option_d, correct_answer, explanation, points)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', questions_data)

        # Seed forum post
        student_id = cursor.execute("SELECT id FROM users WHERE phone = '01111111111'").fetchone()[0]
        cursor.execute('''
            INSERT INTO forum_posts (user_id, course_id, subject, title, content)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            student_id,
            arabic_id,
            'اللغة العربية',
            'سؤال حول الفرق بين اسم المفعول والمصدر الميمي',
            'السلام عليكم يا زملائي والمعلمين الكرام، كيف يمكن التمييز بسهولة بين اسم الزمان واسم المكان واسم المفعول والمصدر الميمي عندما تكون على نفس الوزن من غير الثلاثي؟'
        ))
        post_id = cursor.lastrowid

        admin_id = cursor.execute("SELECT id FROM users WHERE phone = '01000000000'").fetchone()[0]
        cursor.execute('''
            INSERT INTO forum_replies (post_id, user_id, content)
            VALUES (?, ?, ?)
        ''', (
            post_id,
            admin_id,
            'وعليكم السلام ورحمة الله وبركاته يا بني. يمكنك التمييز دائماً من خلال سياق الجملة وقرائن الكلام؛ فإذا دلت الكلمة على من وقع عليه الفعل فهي اسم مفعول، وإذا صح وضع المصدر الصريح مكانها فهي مصدر ميمي، وإذا دلت على زمن أو مكان حدوث الفعل فهي اسم زمان أو مكان.'
        ))

    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()
    print("Database initialized successfully!")
