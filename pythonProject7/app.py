from werkzeug.security import generate_password_hash, check_password_hash
from flask import Flask, render_template, url_for, request, redirect
from flask import session, flash
from datetime import datetime
import json
from pathlib import Path
from data_parser import parse_input
from decision_maker import DecisionMaker
from excel_exporter import ExcelExporter
from flask_sqlalchemy import SQLAlchemy
import os

app = Flask(__name__)
app.secret_key = os.urandom(24)
# Подключение к базе данных
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'kursach.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Инициализация базы
db = SQLAlchemy(app)

# МОДЕЛИ
class Manager(db.Model):
    __tablename__ = 'managers'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

    # Добавляем отношение к запросам
    requests = db.relationship(
        'Request',
        backref='manager',
        cascade='all, delete-orphan',
        lazy='dynamic'
    )
class Request(db.Model):
    __tablename__ = 'requests'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    access_code = db.Column(
        db.String(5),
        unique=True,
        nullable=False
    )
    is_active = db.Column(db.Boolean, default=True)

    # Добавляем внешний ключ для связи с Manager
    manager_id = db.Column(db.Integer, db.ForeignKey('managers.id'), nullable=False)

    # Связи
    experts = db.relationship('Expert', backref='request', cascade='all, delete-orphan')
    alternatives = db.relationship('Alternative', backref='request', cascade='all, delete-orphan')
    criteria = db.relationship('Criterion', backref='request', cascade='all, delete-orphan')

class Expert(db.Model):
    __tablename__ = 'experts'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    contact = db.Column(db.String(100))
    request_id = db.Column(db.Integer, db.ForeignKey('requests.id'), nullable=False)

    # Исправленная связь
    ratings = db.relationship('Rating', back_populates='expert', cascade='all, delete-orphan')


class Scale(db.Model):
    __tablename__ = 'scales'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(20), nullable=False)  # 'numeric' или 'linguistic'
    values = db.Column(db.String(500), nullable=False)  # значения через ;

    # Критерии, использующие эту шкалу
    criteria = db.relationship('Criterion', backref='scale')

class Criterion(db.Model):
    __tablename__ = 'criteria'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    is_qualitative = db.Column(db.Boolean, default=False)
    request_id = db.Column(db.Integer, db.ForeignKey('requests.id'), nullable=False)
    scale_id = db.Column(db.Integer, db.ForeignKey('scales.id'), nullable=False)

    # Исправленная связь
    ratings = db.relationship('Rating', back_populates='criterion')


class Alternative(db.Model):
    __tablename__ = 'alternatives'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    request_id = db.Column(db.Integer, db.ForeignKey('requests.id'), nullable=False)

    # Исправленная связь
    ratings = db.relationship('Rating', back_populates='alternative')


class Rating(db.Model):
    __tablename__ = 'ratings'
    id = db.Column(db.Integer, primary_key=True)
    value = db.Column(db.String(100), nullable=False)
    alternative_id = db.Column(db.Integer, db.ForeignKey('alternatives.id'), nullable=False)
    criterion_id = db.Column(db.Integer, db.ForeignKey('criteria.id'), nullable=False)
    expert_id = db.Column(db.Integer, db.ForeignKey('experts.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Исправленные связи
    alternative = db.relationship('Alternative', back_populates='ratings')
    criterion = db.relationship('Criterion', back_populates='ratings')
    expert = db.relationship('Expert', back_populates='ratings')

class DecisionRequest(db.Model):
    __tablename__ = 'decision_requests'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    result_summary = db.Column(db.String(500))

@app.route('/')
def index_home():
    return render_template("home.html")


@app.route('/about')
def about():
    return render_template("about.html")


@app.route('/instruction')
def instruction():
    return render_template("instruction.html")


@app.route('/expert', methods=["POST", "GET"])
def expert():
    if request.method == "POST":
        expert_name = request.form.get('name', '').strip()
        access_code = request.form.get('psw', '').strip()

        # Валидация ввода
        if not all([expert_name, access_code]):
            flash('Заполните все обязательные поля', 'error')
            return redirect(url_for('expert_error'))

        if len(access_code) != 5 or not access_code.isdigit():
            flash('Код доступа должен состоять из 5 цифр', 'error')
            return redirect(url_for('expert_error'))

        # Поиск запроса
        request_entry = Request.query.filter_by(access_code=access_code).first()

        if not request_entry:
            flash('Неверный код доступа', 'error')
            return redirect(url_for('expert_error'))

        # Проверка эксперта
        expert = Expert.query.filter_by(
            name=expert_name,
            request_id=request_entry.id
        ).first()

        if expert:
            session['expert_id'] = expert.id
            session['request_id'] = request_entry.id
            return redirect(url_for('expert_assessment'))
        else:
            flash('Эксперт не найден в данном запросе', 'error')
            return redirect(url_for('expert'))
    return render_template('expert.html')


@app.route('/expert_assessment', methods=['GET', 'POST'])
def expert_assessment():
    if 'expert_id' not in session or 'request_id' not in session:
        return redirect(url_for('expert'))

    expert_id = session['expert_id']
    request_id = session['request_id']

    expert = Expert.query.get(expert_id)
    alternatives = Alternative.query.filter_by(request_id=request_id).all()

    # Исправлено здесь
    criterias = Criterion.query.filter_by(request_id=request_id).all()

    for criteria in criterias:
        scale = Scale.query.get(criteria.scale_id)
        if scale:
            criteria.scale_values = scale.values.split(';')
            if scale.type == 'numeric':
                criteria.min_val = min(map(float, criteria.scale_values))
                criteria.max_val = max(map(float, criteria.scale_values))
            else:
                criteria.min_val = None
                criteria.max_val = None

    if request.method == 'POST':
        try:
            for alt in alternatives:
                for crit in criterias:
                    field_name = f"rating_{alt.id}_{crit.id}"
                    value = request.form.get(field_name)

                    if value:
                        if crit.scale.type == 'numeric':
                            value = float(value)
                            if not (crit.min_val <= value <= crit.max_val):
                                flash(f'Значение для {crit.name} должно быть между {crit.min_val} и {crit.max_val}',
                                      'error')
                                return redirect(url_for('expert_assessment'))

                        rating = Rating(
                            value=str(value),
                            alternative_id=alt.id,
                            criterion_id=crit.id,
                            expert_id=expert_id
                        )
                        db.session.add(rating)

            db.session.commit()
            flash('Оценки успешно сохранены!', 'success')
            return redirect(url_for('expert_finish'))

        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка сохранения: {str(e)}', 'error')

    return render_template("expert_assessment.html",
                           expert=expert,
                           alternatives=alternatives,
                           criterias=criterias)
@app.route('/expert_finish')
def expert_thankyou():
    if 'expert_id' in session:
        session.pop('expert_id', None)
        session.pop('request_id', None)
    return render_template('expert_finish.html')

@app.route('/expert_error', methods=["POST", "GET"])
def expert_error():
    return render_template('expert_error.html')


@app.route('/manager')
def manager():
    return render_template("manager.html")


@app.route('/manager_login', methods=['GET', 'POST'])
def manager_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        manager = Manager.query.filter_by(username=username).first()
        if manager and check_password_hash(manager.password_hash, password):
            session['manager_id'] = manager.id
            return redirect('/manager_menu')
        else:
            return redirect('/manager_login_error')

    return render_template("manager_login.html")

@app.route('/manager_createacc', methods=['GET','POST'])
def manager_createacc():
    error = None

    if request.method == 'POST':

        username = request.form.get('name')
        password = request.form.get('psw')
        confirm_password = request.form.get('psw1')

        if password != confirm_password:
            error = "Пароли не совпадают"
        elif Manager.query.filter_by(username=username).first():
            error = "Пользователь уже существует"
        else:
            password_hash = generate_password_hash(password)
            new_manager = Manager(username=username, password_hash=password_hash)
            db.session.add(new_manager)
            db.session.commit()
            return redirect('/manager_menu')

    return render_template("manager_createacc.html", error=error)


@app.route('/manager_login_error', methods=['GET', 'POST'])
def manager_login_error():
    return render_template("manager_login_error.html")


@app.route('/manager_createacc_error', methods=['GET', 'POST'])
def manager_createacc_error():
    return render_template("manager_createacc_error.html")


@app.route('/manager_menu')
def manager_menu():
    return render_template("manager_menu.html")


@app.route('/expert_finish')
def expert_finish():
    return render_template("expert_finish.html")
@app.route('/manager_request', methods=['GET', 'POST'])
def manager_request():
    if request.method == 'POST':
        if 'manager_id' not in session:
            return redirect(url_for('manager_login'))

        access_code = request.form.get('access_code', '').strip()
        name = request.form.get('name', '').strip()

            # Валидация полей
        if not all([name, access_code]):
            flash('Заполните все обязательные поля', 'error')
            return redirect(url_for('manager_request'))

        if len(access_code) != 5 or not access_code.isdigit():
            flash('Код должен состоять из 5 цифр', 'error')
            return redirect(url_for('manager_request'))

        try:
            new_request = Request(
                name=name,
                manager_id=session['manager_id'],
                access_code=access_code,
                is_active=True
            )

            db.session.add(new_request)
            db.session.commit()

            session['request_data'] = {
                'request_id': new_request.id,
                'num_experts': request.form.get('experts'),
                'num_criterias': request.form.get('criterias'),
                'num_scales': request.form.get('scales'),
                'num_alternatives': request.form.get('alternatives')
            }

            return redirect(url_for('manager_request_experts'))

        except IntegrityError:
            db.session.rollback()
            flash('Этот код доступа уже используется', 'error')
            return redirect(url_for('manager_request_error'))

        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при создании запроса: {str(e)}', 'error')
            return redirect(url_for('manager_request'))

    return render_template("manager_request.html")

@app.route('/manager_request_error')
def manager_request_error():
    return render_template("manager_request_error.html")


@app.route('/manager_request_finish')
def manager_request_finish():
    return render_template("manager_request_finish.html")


@app.route('/manager_request_experts', methods=['GET', 'POST'])
def manager_request_experts():
    # Проверяем наличие данных в сессии
    if 'request_data' not in session or 'request_id' not in session['request_data']:
        return redirect('/manager_request')

    request_data = session['request_data']
    total = int(request_data['num_experts'])
    request_id = session['request_data']['request_id']

    if request.method == 'POST':
        try:
            for i in range(total):
                name = request.form.get(f'name_{i}')
                competence = request.form.get(f'competence_{i}')

                # Создаем эксперта с привязкой к запросу
                new_expert = Expert(
                    name=name,
                    contact=competence,
                    request_id=request_id  # Используем ID из сессии
                )
                db.session.add(new_expert)

            db.session.commit()
            return redirect('/manager_request_scales')

        except Exception as e:
            db.session.rollback()

            return redirect('/manager_request_experts')

    return render_template('manager_request_experts.html', count=total)

@app.route('/manager_request_experts_error')
def manager_request_experts_error():
    request_data = session['request_data']
    total = int(request_data['num_experts'])
    request_id = session['request_data']['request_id']
    return render_template("manager_request_experts_error.html", count = total)

@app.route('/manager_request_scales', methods=['GET', 'POST'])
def manager_request_scales():
    request_data = session.get('request_data', {})
    total = int(request_data.get('num_scales', 1))

    if request.method == 'POST':
        try:
            scales = []
            for i in range(total):
                scale_name = request.form.get(f'scale_name_{i}', '').strip()
                scale_type = request.form.get(f'scale_type_{i}', 'linguistic')
                raw_values = request.form.get(f'scale_values_{i}', '').strip()

                # Валидация данных
                if not all([scale_name, scale_type, raw_values]):
                    flash('Заполните все поля для всех шкал', 'error')
                    return redirect(url_for('manager_request_scales'))

                # Обработка значений
                values = [v.strip() for v in raw_values.split(';') if v.strip()]
                values_str = ";".join(values)

                # Проверка максимальной длины
                if len(values_str) > 500:
                    flash('Максимальная длина значений шкалы - 500 символов', 'error')
                    return redirect(url_for('manager_request_scales'))

                # Проверка количества значений
                if len(values) > 10:
                    flash('Максимум 10 значений в одной шкале', 'error')
                    return redirect(url_for('manager_request_scales'))

                # Проверка числовых значений
                if scale_type == 'numeric':
                    try:
                        [float(v) for v in values]
                    except ValueError:
                        flash('Для числовой шкалы вводите только числа', 'error')
                        return redirect(url_for('manager_request_scales'))

                # Создание шкалы
                scales.append(Scale(
                    name=scale_name,
                    type=scale_type,  # Используем новое имя поля
                    values=values_str
                ))

            db.session.bulk_save_objects(scales)
            db.session.commit()
            flash('Все шкалы успешно сохранены', 'success')
            return redirect(url_for('manager_request_criterias'))

        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при сохранении: {str(e)}', 'error')
            return redirect(url_for('manager_request_scales'))

    return render_template('manager_request_scales.html', count=total)


@app.route('/manager_request_scales_error')
def manager_request_scales_error():
    request_data = session.get('request_data', {})
    total = int(request_data.get('num_scales', 1))
    return render_template("manager_request_scales_error.html", count=total)


@app.route('/manager_request_criterias', methods=['GET', 'POST'])
def manager_request_criterias():
    if 'request_data' not in session or 'request_id' not in session['request_data']:
        flash('Сначала создайте запрос', 'error')
        return redirect(url_for('manager_request'))

    try:
        request_id = session['request_data']['request_id']
        count = int(session['request_data'].get('num_criterias', 1))
    except (KeyError, TypeError, ValueError) as e:
        flash('Ошибка получения данных сессии', 'error')
        return redirect(url_for('manager_request'))

    scales = Scale.query.all()

    if request.method == 'POST':
        try:
            criteria = []
            for i in range(count):
                name = request.form.get(f'name_{i}', '').strip()
                is_qual = request.form.get(f'is_qualitative_{i}', 'off') == 'on'
                scale_id = request.form.get(f'scale_{i}')

                if not all([name, scale_id]):
                    flash(f'Заполните все поля для критерия {i + 1}', 'error')
                    continue

                # Проверяем существование шкалы
                if not Scale.query.get(scale_id):
                    flash(f'Выбрана несуществующая шкала для критерия {i + 1}', 'error')
                    continue

                criteria.append(Criterion(
                    name=name,
                    is_qualitative=is_qual,
                    request_id=request_id,  # Добавляем привязку к запросу
                    scale_id=scale_id
                ))

            db.session.bulk_save_objects(criteria)
            db.session.commit()
            flash('Все критерии успешно сохранены!', 'success')
            return redirect(url_for('manager_request_alternatives'))

        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка сохранения: {str(e)}', 'error')
            app.logger.error(f'Error saving criteria: {str(e)}')

    return render_template('manager_request_criterias.html', count=count, scales=scales)

@app.route('/manager_request_criterias_error')
def manager_request_criterias_error():
    request_id = session['request_data']['request_id']
    count = int(session['request_data'].get('num_criterias', 1))
    scales = Scale.query.all()
    return render_template("manager_request_criterias_error.html", count=count, scales=scales)


@app.route('/manager_request_alternatives', methods=['GET', 'POST'])
def manager_request_alternatives():
    # Проверяем наличие данных в сессии
    if 'request_data' not in session or 'request_id' not in session['request_data']:
        flash('Сначала создайте запрос', 'error')
        return redirect(url_for('manager_request'))

    try:
        request_id = session['request_data']['request_id']
        num_alternatives = int(session['request_data'].get('num_alternatives', 1))
    except (KeyError, ValueError, TypeError) as e:
        flash('Ошибка получения данных', 'error')
        return redirect(url_for('manager_request'))

    if request.method == 'POST':
        try:
            alternatives = []
            for i in range(num_alternatives):
                name = request.form.get(f'alt_{i}', '').strip()
                if name:
                    alternatives.append(Alternative(
                        name=name,
                        request_id=request_id  # Добавляем привязку к запросу
                    ))

            if not alternatives:
                flash('Введите хотя бы одну альтернативу!', 'error')
                return redirect(url_for('manager_request_alternatives'))

            db.session.bulk_save_objects(alternatives)
            db.session.commit()
            flash('Альтернативы успешно сохранены!', 'success')
            return redirect(url_for('manager_archive'))

        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка сохранения: {str(e)}', 'error')
            app.logger.error(f'Error saving alternatives: {str(e)}')

    return render_template('manager_request_alternatives.html', count=num_alternatives)

@app.route('/manager_request_alternatives_error')
def manager_request_alternatives_error():
    request_id = session['request_data']['request_id']
    num_alternatives = int(session['request_data'].get('num_alternatives', 1))
    return render_template("manager_request_alternatives_error.html",  count=num_alternatives)


@app.route('/manager_archive')
def manager_archive():
    # Проверяем авторизацию менеджера
    if 'manager_id' not in session:
        return redirect(url_for('manager_login'))

    # Получаем все запросы менеджера
    manager = Manager.query.get(session['manager_id'])
    requests = Request.query.filter_by(manager=manager) \
        .order_by(Request.created_at.desc()).all()

    return render_template("manager_archive.html", requests=requests)

@app.route('/send_decision', methods=['POST'])
def send_decision():
    import json
    import requests

    with open("decision_input.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    try:
        response = requests.post("http://127.0.0.1:1234/api/v1/make-decision", json=data)
        response.raise_for_status()
        result = response.json()

        with open("decision_result.json", "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=4)

        summary = ", ".join([f"{item['alternative']} → {item['score']}" for item in result])
        new_req = DecisionRequest(title="Новый запрос", result_summary=summary)
        db.session.add(new_req)
        db.session.commit()

        return redirect("/decision_result")

    except requests.RequestException as e:
        return f"Ошибка при отправке в решатель: {str(e)}", 500


@app.route('/decision_result')
def decision_result():
    import json
    try:
        with open("decision_result.json", "r", encoding="utf-8") as f:
            result = json.load(f)
    except FileNotFoundError:
        result = []
    return render_template("decision_result.html", result=result)

def main():
    try:
        # 1. Загрузка данных
        input_path = Path('input.json')
        print(f"[INFO] Загрузка данных из {input_path}")
        input_data = parse_input(input_path)

        # 2. Расчет результатов
        print("[INFO] Расчет результатов...")
        dm = DecisionMaker(input_data)
        results = dm.calculate()

        # 3. Экспорт в Excel
        output_path = Path('results.xlsx')
        print(f"[INFO] Экспорт в {output_path}")
        ExcelExporter(results).export(output_path)

        print(f"[INFO] Результаты сохранены в {output_path}")

    except Exception as e:
        print(f"[FATAL] Критическая ошибка: {str(e)}")

if __name__ == "__main__":
    app.run(debug=True)