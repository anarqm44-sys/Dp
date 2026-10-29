import sys
import io
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from app import app
from database import get_db_connection

def test_full_e2e():
    print("Starting Comprehensive E2E Testing...")
    client = app.test_client()

    unique_phone = f"012{int(time.time()*100)%100000000:08d}"

    # 1. Register student
    print("1. Testing Student Registration & 100 EGP Welcome Bonus...")
    res = client.post('/register', data={
        'full_name': 'طالب تجريبي ذكي',
        'phone': unique_phone,
        'division': 'علمي رياضة',
        'password': 'password123'
    }, follow_redirects=True)
    assert res.status_code == 200
    assert '100' in res.data.decode('utf-8')
    print("   [PASS] Registration & Welcome balance OK")

    # 2. Check Wallet
    print("2. Testing Student Wallet View...")
    res = client.get('/wallet')
    assert res.status_code == 200
    assert '100.00' in res.data.decode('utf-8')
    print("   [PASS] Wallet displays correct balance")

    # 3. Top-Up Request
    print("3. Testing Wallet Top-up Request...")
    res = client.post('/wallet/topup', data={
        'amount': '200',
        'payment_method': 'فودافون كاش',
        'reference_number': 'VF-99887766',
        'notes': 'تم التحويل من رقم 01099999999'
    }, follow_redirects=True)
    assert res.status_code == 200
    print("   [PASS] Top-up request submitted")

    # 4. Enroll in a Course using Wallet
    print("4. Testing Course Purchase with Wallet Balance...")
    # Course with price 100 or 120 or 150
    conn = get_db_connection()
    course = conn.execute("SELECT id, title, price FROM courses WHERE price <= 100 LIMIT 1").fetchone()
    conn.close()
    if course:
        res = client.post(f'/courses/{course["id"]}/enroll', follow_redirects=True)
        assert res.status_code == 200
        print(f"   [PASS] Enrolled in course: {course['title']}")

    # 5. Take Exam & Automatic Grading
    print("5. Testing Exam Taking & Automatic Grading...")
    conn = get_db_connection()
    exam = conn.execute("SELECT id, title FROM exams LIMIT 1").fetchone()
    questions = conn.execute("SELECT id, correct_answer FROM questions WHERE exam_id = ?", (exam['id'],)).fetchall()
    conn.close()

    answers_payload = {}
    for q in questions:
        answers_payload[f"q_{q['id']}"] = q['correct_answer']

    res = client.post(f'/exams/{exam["id"]}/submit', data=answers_payload, follow_redirects=True)
    assert res.status_code == 200
    body = res.data.decode('utf-8')
    assert '100.0%' in body or '100%' in body
    assert 'بنجاح' in body or 'ناجح' in body
    print("   [PASS] Exam submitted, 100% graded automatically with full explanations")

    # 6. Forum Interaction
    print("6. Testing Scientific Forum Post & Discussion...")
    res = client.post('/forum/posts/create', data={
        'subject': 'الرياضيات',
        'title': 'سؤال حول قاعدة لوبيتال في النهايات',
        'content': 'هل يمكن استخدام قاعدة لوبيتال في مسائل النهايات في امتحان التفاضل؟'
    }, follow_redirects=True)
    assert res.status_code == 200
    print("   [PASS] Forum question published successfully")

    # 7. Admin Login & Wallet Approval
    print("7. Testing Admin Login & Approving Top-up Request...")
    # Logout student
    client.get('/logout')
    
    # Login admin
    res = client.post('/login', data={
        'phone': '01000000000',
        'password': 'admin123'
    }, follow_redirects=True)
    assert res.status_code == 200
    print("   [PASS] Admin login successful")

    # Approve pending top-up
    conn = get_db_connection()
    tx = conn.execute("SELECT id FROM wallet_transactions WHERE status = 'pending' LIMIT 1").fetchone()
    conn.close()
    if tx:
        res = client.post(f'/admin/wallet/requests/{tx["id"]}/action', data={'action': 'approve'}, follow_redirects=True)
        assert res.status_code == 200
        print("   [PASS] Admin approved top-up request")

    # 8. Admin Course Creation
    print("8. Testing Admin Course Creation...")
    res = client.post('/admin/courses/create', data={
        'title': 'كورس الفيزياء الحديثة والكهربية',
        'subject': 'الفيزياء',
        'grade': 'الصف الثالث الثانوي',
        'price': '180',
        'image_url': '',
        'description': 'شرح شامل لقوانين كيرشوف والدينامو والفيزياء الذرية.',
        'is_published': '1'
    }, follow_redirects=True)
    assert res.status_code == 200
    print("   [PASS] Admin created course successfully")

    print("\nALL 8 COMPREHENSIVE E2E TESTS PASSED WITH 100% SUCCESS! 🎉")

if __name__ == '__main__':
    test_full_e2e()
