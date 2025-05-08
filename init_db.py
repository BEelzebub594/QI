from app import app, db
from models import User

def init_db():
    with app.app_context():
        # 创建所有表
        db.create_all()
        
        # 创建一个测试用户
        if not User.query.filter_by(username='admin').first():
            user = User(username='admin', email='admin@example.com')
            user.set_password('admin123')
            db.session.add(user)
            db.session.commit()
            print('Created test user: admin/admin123')

if __name__ == '__main__':
    init_db()
    print('Database initialized successfully!') 