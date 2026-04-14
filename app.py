from flask import Flask, render_template, request, redirect, url_for
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from models import User
from db import db

app = Flask(__name__)
app.secret_key = 'secret_key'
lm = LoginManager(app)
lm.login_view = 'landing'
app.config['SQLALCHEMY_DATABASE_URI'] = "sqlite:///database.db"
db.init_app(app)

@lm.user_loader
def user_loader(id):
    user = db.session.query(User).filter_by(id=id).first()
    return user

@app.route('/')
@login_required
def home():
    return render_template('home.html')

@app.route('/landing')
def landing():
    return render_template('landing.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('login.html')
    elif request.method == 'POST':
        mail = request.form['mailForm']
        password = request.form['passwordForm']

        user = db.session.query(User).filter_by(mail=mail, password=password).first()
        if not user:
            return 'Email ou senha incorretos.'
        
        login_user(user)
        return redirect(url_for('home'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'GET':
        return render_template('register.html')
    elif request.method == 'POST':
        name = request.form['nameForm']
        mail = request.form['mailForm']
        password = request.form['passwordForm']

        new_user = User(name=name, mail=mail, password=password)
        db.session.add(new_user)
        db.session.commit()

        login_user(new_user)

        return redirect(url_for('home'))
    
@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'GET':
        return render_template('profile.html', user=current_user)
    elif request.method == 'POST':
        name = request.form['nameForm'].strip() or current_user.name
        mail = request.form['mailForm'].strip() or current_user.mail
        password = request.form['passwordForm'].strip() or current_user.password

        current_user.name = name
        current_user.mail = mail
        current_user.password = password

        db.session.commit()

        return redirect(url_for('home'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)