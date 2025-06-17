# app.py
from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date, timedelta
from notify import send_line_notify

app = Flask(__name__)
import os
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {"connect_args": {"sslmode": "require"}}
db = SQLAlchemy(app)

# 資料模型
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80))
    email = db.Column(db.String(120))
    accounts = db.relationship('Account', backref='user', lazy=True)

class Account(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    balance = db.Column(db.Float, default=0.0)
    interest_rate = db.Column(db.Float, default=1.0)
    payout_cycle = db.Column(db.String(20), default='monthly')
    transactions = db.relationship('Transaction', backref='account', lazy=True, cascade="all, delete-orphan")

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=False)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    type = db.Column(db.String(20))
    amount = db.Column(db.Float)
    note = db.Column(db.String(200))
    balance_after = db.Column(db.Float)

@app.route('/')
def index():
    accounts = Account.query.all()
    users = User.query.all()
    return render_template('index.html', accounts=accounts, users=users)

@app.route('/account/<int:account_id>')
def account_detail(account_id):
    account = Account.query.get_or_404(account_id)
    return render_template('detail.html', account=account)

@app.route('/transaction', methods=['POST'])
def add_transaction():
    account_id = int(request.form['account_id'])
    t_type = request.form['type']
    amount = float(request.form['amount'])
    note = request.form['note']

    account = Account.query.get_or_404(account_id)
    if t_type == 'deposit':
        account.balance += amount
    elif t_type == 'withdraw' and account.balance >= amount:
        account.balance -= amount
    else:
        return "Insufficient funds or invalid type"

    new_tx = Transaction(account_id=account_id, type=t_type, amount=amount, note=note)
    db.session.add(new_tx)
    db.session.commit()

    send_line_notify(f"帳戶更新: {t_type} ${amount}\n帳戶ID: {account_id} 餘額: ${account.balance:.2f}")

    return redirect(url_for('account_detail', account_id=account_id))

@app.route('/interest')
def run_interest():
    today = date.today()
    if today.day != 25:
        return "今天不是配息日"
    accounts = Account.query.all()
    for acc in accounts:
        if acc.payout_cycle == 'monthly':
            monthly_rate = acc.interest_rate / 12 / 100
            interest = int(acc.balance * monthly_rate)
            acc.balance += interest
            tx = Transaction(account_id=acc.id, type='interest', amount=interest, note='月配息')
            db.session.add(tx)
            send_line_notify(f"月配息通知: 帳戶 {acc.id} 入息 ${interest:.2f}")
    db.session.commit()
    return "配息完成"

@app.route('/new_account', methods=['POST'])
def new_account():
    user_id = int(request.form['user_id'])
    balance = float(request.form['balance'])
    interest_rate = float(request.form['interest_rate'])
    payout_cycle = request.form['payout_cycle']
    date_str = request.form.get('deposit_date')

    acc = Account(user_id=user_id, balance=balance, interest_rate=interest_rate, payout_cycle=payout_cycle)
    db.session.add(acc)
    db.session.commit()

    # 處理存入日期（預設為今天）
    try:
        tx_date = datetime.strptime(date_str, "%Y-%m-%d") if date_str else datetime.utcnow()
    except ValueError:
        tx_date = datetime.utcnow()

    # 建立初始存入交易
    tx = Transaction(
        account_id=acc.id,
        type='deposit',
        amount=balance,
        note='初始存入',
        date=tx_date,
        balance_after=acc.balance
    )
    db.session.add(tx)

    # 建立歷史月配息交易（僅當日期早於今天）
    if payout_cycle == 'monthly' and tx_date.date() < date.today():
        monthly_rate = interest_rate / 12 / 100
        current_date = tx_date.date()

        # 從下個 25 號開始
        if current_date.day > 25:
            current_date = (current_date.replace(day=1) + timedelta(days=32)).replace(day=25)
        else:
            current_date = current_date.replace(day=25)

        current_balance = balance

        while current_date < date.today():
            interest = int(current_balance * monthly_rate)  # 去掉小數點
            current_balance += interest
            acc.balance += interest
            interest_tx = Transaction(
                account_id=acc.id,
                type='interest',
                amount=interest,
                note='歷史月配息',
                date=datetime(current_date.year, current_date.month, 25),
                balance_after=acc.balance
            )
            db.session.add(interest_tx)
            # 前往下個月
            next_month = current_date.replace(day=1) + timedelta(days=32)
            current_date = next_month.replace(day=25)

    db.session.commit()
    return redirect(url_for('index'))


@app.route('/delete_account/<int:account_id>', methods=['POST'])
def delete_account(account_id):
    account = Account.query.get_or_404(account_id)
    db.session.delete(account)
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/new_user', methods=['POST'])
def new_user():
    name = request.form['name']
    email = request.form['email']
    user = User(name=name, email=email)
    db.session.add(user)
    db.session.commit()
    return redirect(url_for('index'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host="0.0.0.0", port=port)
