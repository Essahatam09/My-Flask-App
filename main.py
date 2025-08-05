import os
import re
import uuid
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import or_
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'EssaKey'  # Change this to a strong secret in production!

# Setup SQLite DB
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Upload configuration
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

db = SQLAlchemy(app)

# User model
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    profile_pic = db.Column(db.String(120), nullable=True)  # New field for profile picture filename

# Anime model linked to User
class Anime(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    episodes = db.Column(db.Integer, default=0)
    note = db.Column(db.Text, nullable=True)  # note before watching or general note
    image = db.Column(db.String(200), nullable=True)  # filename of uploaded image
    rating = db.Column(db.Float, default=0.0)  # 1.0 to 10.0
    genre = db.Column(db.String(100), nullable=True)
    status = db.Column(db.String(50), nullable=False)  # 'Watched', 'Favorite', 'Plan to Watch', 'Dropped'

    user = db.relationship('User', backref=db.backref('animes', lazy=True))


# Create DB tables (run once at startup)
with app.app_context():
    db.create_all()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form['name'].strip()
        username = request.form['username'].strip()
        email = request.form['email'].strip()
        password_raw = request.form['password']

        if len(password_raw) < 8:
            flash("Password must be at least 8 characters long.", "error")
        elif not re.search(r"[A-Z]", password_raw):
            flash("Password must contain at least one uppercase letter.", "error")
        elif not re.search(r"[0-9]", password_raw):
            flash("Password must contain at least one number.", "error")
        elif not re.search(r"[@$&]", password_raw):
            flash("Password must contain at least one special character (@, $, &).", "error")
        elif User.query.filter((User.username == username) | (User.email == email)).first():
            flash("Username or email already registered.", "error")
        else:
            hashed_password = generate_password_hash(password_raw)
            new_user = User(name=name, username=username, email=email, password=hashed_password)
            db.session.add(new_user)
            db.session.commit()
            flash("Signup successful! You can now log in.", "success")
            return redirect(url_for('login'))

    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user_input = request.form['username'].strip()
        password = request.form['password']

        user = User.query.filter(
            or_(User.username == user_input, User.email == user_input)
        ).first()

        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            session['username'] = user.username
            flash(f"Welcome back, {user.name}!", "success")
            return redirect(url_for('home'))
        else:
            flash("Invalid username/email or password.", "error")

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for('login'))

@app.route('/home')
def home():
    user_id = session.get('user_id')
    if not user_id:
        flash("Please log in first.", "error")
        return redirect(url_for('login'))

    user = User.query.get(user_id)
    if not user:
        flash("User not found. Please log in again.", "error")
        session.clear()
        return redirect(url_for('login'))

    return render_template('home.html', user=user)


# Updated animelist route with real data and stats
@app.route('/animelist')
def animelist():
    user_id = session.get('user_id')
    if not user_id:
        flash("Please log in first.", "error")
        return redirect(url_for('login'))

    user = User.query.get(user_id)
    if not user:
        flash("User not found.", "error")
        session.clear()
        return redirect(url_for('login'))

    # Query anime by status
    watched = Anime.query.filter_by(user_id=user_id, status='Watched').all()
    favorite = Anime.query.filter_by(user_id=user_id, status='Favorite').all()
    plan_to_watch = Anime.query.filter_by(user_id=user_id, status='Plan to Watch').all()
    dropped = Anime.query.filter_by(user_id=user_id, status='Dropped').all()

    # Stats for dashboard
    total_animes = len(watched) + len(favorite) + len(plan_to_watch) + len(dropped)
    ratings = [anime.rating for anime in watched + favorite if anime.rating > 0]
    avg_rating = round(sum(ratings) / len(ratings), 2) if ratings else 0

    total_episodes = sum(anime.episodes for anime in watched)
    total_time_watched = total_episodes * 24  # Approximate minutes per episode

    return render_template('animelist.html',
                           user=user,
                           watched=watched,
                           favorite=favorite,
                           plan_to_watch=plan_to_watch,
                           dropped=dropped,
                           total_animes=total_animes,
                           avg_rating=avg_rating,
                           total_time_watched=total_time_watched)


# API endpoint to add anime
@app.route('/animelist/add', methods=['POST'])
def add_anime():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401

    title = request.form.get('title', '').strip()
    episodes = request.form.get('episodes', 0)
    note = request.form.get('note', '').strip()
    rating = request.form.get('rating', 0)
    status = request.form.get('status', 'Plan to Watch')
    genre = request.form.get('genre', '').strip()

    if not title:
        return jsonify({"error": "Title is required"}), 400

    try:
        episodes = int(episodes)
    except:
        episodes = 0

    try:
        rating = float(rating)
    except:
        rating = 0.0

    image_file = request.files.get('image')
    image_filename = None
    if image_file and allowed_file(image_file.filename):
        filename = secure_filename(image_file.filename)
        unique_filename = f"{uuid.uuid4().hex}_{filename}"
        image_file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_filename))
        image_filename = unique_filename

    new_anime = Anime(
        user_id=user_id,
        title=title,
        episodes=episodes,
        note=note,
        rating=rating,
        status=status,
        genre=genre,
        image=image_filename
    )
    db.session.add(new_anime)
    db.session.commit()

    return jsonify({"success": True, "anime": {
        "id": new_anime.id,
        "title": new_anime.title,
        "episodes": new_anime.episodes,
        "note": new_anime.note,
        "rating": new_anime.rating,
        "status": new_anime.status,
        "genre": new_anime.genre,
        "image": new_anime.image
    }})


# API endpoint to edit anime
@app.route('/animelist/edit/<int:anime_id>', methods=['POST'])
def edit_anime(anime_id):
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401

    anime = Anime.query.get(anime_id)
    if not anime or anime.user_id != user_id:
        return jsonify({"error": "Anime not found or access denied"}), 404

    title = request.form.get('title', '').strip()
    episodes = request.form.get('episodes', 0)
    note = request.form.get('note', '').strip()
    rating = request.form.get('rating', 0)
    status = request.form.get('status', 'Plan to Watch')
    genre = request.form.get('genre', '').strip()

    if title:
        anime.title = title

    try:
        anime.episodes = int(episodes)
    except:
        anime.episodes = 0

    anime.note = note

    try:
        anime.rating = float(rating)
    except:
        anime.rating = 0.0

    anime.status = status
    anime.genre = genre

    image_file = request.files.get('image')
    if image_file and allowed_file(image_file.filename):
        filename = secure_filename(image_file.filename)
        unique_filename = f"{uuid.uuid4().hex}_{filename}"
        image_file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_filename))
        anime.image = unique_filename

    db.session.commit()
    return jsonify({"success": True})


# API endpoint to delete anime
@app.route('/animelist/delete/<int:anime_id>', methods=['POST'])
def delete_anime(anime_id):
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401

    anime = Anime.query.get(anime_id)
    if not anime or anime.user_id != user_id:
        return jsonify({"error": "Anime not found or access denied"}), 404

    db.session.delete(anime)
    db.session.commit()

    return jsonify({"success": True})


@app.route('/upload_profile_pic', methods=['POST'])
def upload_profile_pic():
    user_id = session.get('user_id')
    if not user_id:
        flash("Please log in first.", "error")
        return redirect(url_for('login'))

    if 'profile_pic' not in request.files:
        flash("No file part in the request.", "error")
        return redirect(url_for('home'))

    file = request.files['profile_pic']
    if file.filename == '':
        flash("No file selected.", "error")
        return redirect(url_for('home'))

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filename = f"user_{user_id}_" + filename
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)

        user = User.query.get(user_id)
        user.profile_pic = filename
        db.session.commit()

        flash("Profile picture updated successfully!", "success")
        return redirect(url_for('home'))
    else:
        flash("Allowed image types are - png, jpg, jpeg, gif", "error")
        return redirect(url_for('home'))

@app.route('/edit_profile', methods=['GET', 'POST'])
def edit_profile():
    user = User.query.get(session['user_id'])

    if request.method == 'POST':
        name = request.form.get('name')
        username = request.form.get('username')
        email = request.form.get('email')
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')

        # Update text fields
        user.name = name
        user.username = username
        user.email = email

        # Handle password change only if new_password is provided
        if new_password:
            if not check_password_hash(user.password, current_password):
                flash("Current password is incorrect.", "error")
                return render_template('edit_profile.html', user=user)

            if len(new_password) < 8:
                flash("New password must be at least 8 characters long.", "error")
                return render_template('edit_profile.html', user=user)
            elif not re.search(r"[A-Z]", new_password):
                flash("New password must contain an uppercase letter.", "error")
                return render_template('edit_profile.html', user=user)
            elif not re.search(r"[0-9]", new_password):
                flash("New password must contain a number.", "error")
                return render_template('edit_profile.html', user=user)
            elif not re.search(r"[@$&]", new_password):
                flash("New password must contain @, $, or &.", "error")
                return render_template('edit_profile.html', user=user)
            else:
                user.password = generate_password_hash(new_password)

        # Handle profile picture upload
        profile_pic = request.files.get('profile_pic')
        if profile_pic and profile_pic.filename != '':
            filename = secure_filename(profile_pic.filename)
            unique_filename = str(uuid.uuid4()) + "_" + filename
            profile_pic.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_filename))
            user.profile_pic = unique_filename

        db.session.commit()
        flash("Profile updated successfully!", "success")
        return redirect(url_for('home'))

    return render_template('edit_profile.html', user=user)

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404
@app.route('/api/animelist')
def api_animelist():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401
    animes = Anime.query.filter_by(user_id=user_id).all()
    data = []
    for a in animes:
        data.append({
            "id": a.id,
            "title": a.title,
            "genre": a.genre or "",  # comma-separated string as frontend expects
            "status": a.status,
            "episodes": a.episodes,
            "watchedEpisodes": a.episodes if a.status == 'Watched' else 0,
            "rating": a.rating,
            "note": a.note or "",
            "favorite": (a.status == 'Favorite'),
            "image": a.image if a.image else None,
            # You don’t need to build full URL here, frontend prepends static path
        })
    return jsonify({"animes": data})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)