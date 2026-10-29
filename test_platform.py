import sys
import io

# Set stdout to UTF-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from app import app
from database import get_db_connection

def test_system():
    print("Testing database connection...")
    conn = get_db_connection()
    user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    course_count = conn.execute("SELECT COUNT(*) FROM courses").fetchone()[0]
    exam_count = conn.execute("SELECT COUNT(*) FROM exams").fetchone()[0]
    question_count = conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
    conn.close()

    print(f"Users in DB: {user_count}")
    print(f"Courses in DB: {course_count}")
    print(f"Exams in DB: {exam_count}")
    print(f"Questions in DB: {question_count}")

    print("\nTesting Flask test client...")
    client = app.test_client()
    
    # Test Index
    res = client.get('/')
    assert res.status_code == 200, f"Expected 200 on /, got {res.status_code}"
    assert 'سهلتهالك' in res.data.decode('utf-8')
    print("[OK] Landing page (/)")

    # Test Courses List
    res = client.get('/courses')
    assert res.status_code == 200
    print("[OK] Courses page (/courses)")

    # Test Exams List
    res = client.get('/exams')
    assert res.status_code == 200
    print("[OK] Exams page (/exams)")

    # Test Forum
    res = client.get('/forum')
    assert res.status_code == 200
    print("[OK] Forum page (/forum)")

    # Test Login page
    res = client.get('/login')
    assert res.status_code == 200
    print("[OK] Login page (/login)")

    print("\nALL PLATFORM TESTS PASSED SUCCESSFULLY!")

if __name__ == '__main__':
    test_system()

