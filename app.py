import os
import uuid
import json

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename

# ---------------- App Setup ----------------------
app = Flask(__name__)
CORS(app)  # ok for local dev

# ---------------- Database -----------------------
DATABASE_URL = "postgresql://postgres:zehra2006@127.0.0.1:5432/recipe_backend"
app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ECHO"] = True

db = SQLAlchemy(app)

# ---------------- Upload Config ------------------
UPLOAD_FOLDER = os.path.join(app.root_path, "uploads")  # absolute path
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp", "avif"}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def ensure_upload_folder():
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)


def parse_list_field(value):
    """
    Accepts:
    - JSON string: '["a","b"]'
    - python list already
    - comma/newline separated string: "a,b" or "a\nb"
    Returns list[str]
    """
    if value is None:
        return []

    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]

    if isinstance(value, str):
        s = value.strip()
        if not s:
            return []
        # try JSON first
        try:
            parsed = json.loads(s)
            if isinstance(parsed, list):
                return [str(x).strip() for x in parsed if str(x).strip()]
        except Exception:
            pass

        # fallback: split by newlines/commas
        parts = []
        for line in s.replace(",", "\n").split("\n"):
            t = line.strip()
            if t:
                parts.append(t)
        return parts

    return []


# ---------------- Routes -------------------------
@app.route("/")
def home():
    return "Pocket Chef API is running!"


@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    # This lets the browser load: http://127.0.0.1:5000/uploads/xxx.jpg
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


# ---------------- Models -------------------------
class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), default="user")


class Recipe(db.Model):
    __tablename__ = "recipes"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(80))
    prepTime = db.Column(db.Integer)
    image = db.Column(db.Text)
    ingredients = db.Column(db.JSON)
    steps = db.Column(db.JSON)
    likes = db.Column(db.Integer, default=0)
    author = db.Column(db.String(80))
    rating = db.Column(db.Integer, default=0)


class Favorite(db.Model):
    __tablename__ = "favorites"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    recipe_id = db.Column(db.Integer, db.ForeignKey("recipes.id"))

class Like(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipes.id'))


class Comment(db.Model):
    __tablename__ = "comments"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    recipe_id = db.Column(db.Integer, db.ForeignKey("recipes.id"))
    content = db.Column(db.Text)


# ---------------- Recipes ------------------------
@app.route("/recipes", methods=["GET"])
def get_recipes():
    recipes = Recipe.query.all()
    return jsonify([
        {
            "id": r.id,
            "title": r.title,
            "category": r.category,
            "prepTime": r.prepTime,
            "image": r.image or "",
            "ingredients": r.ingredients or [],
            "steps": r.steps or [],
            "likes": r.likes or 0,
            "author": r.author or "",
            "rating": r.rating or 0,
        }
        for r in recipes
    ])


@app.route("/recipes", methods=["POST"])
def add_recipe():
    ensure_upload_folder()

    # IMPORTANT: With FormData, values are in request.form and files in request.files
    data = request.form.to_dict()

    # required fields
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "title is required"}), 400

    category = (data.get("category") or "").strip()
    author = (data.get("author") or "").strip()

    # numbers safe
    try:
        prep_time = int(data.get("prepTime") or 0)
    except:
        prep_time = 0

    # rating default 0
    try:
        rating = int(data.get("rating") or 0)
    except:
        rating = 0

    # likes default 0
    try:
        likes = int(data.get("likes") or 0)
    except:
        likes = 0

    # lists
    ingredients = parse_list_field(data.get("ingredients"))
    steps = parse_list_field(data.get("steps"))

    # -------- Image: file OR URL --------
    image_url = (data.get("image") or "").strip()

    # If a file is present, prefer it over URL
    file = request.files.get("image")
    if file and file.filename:
        if not allowed_file(file.filename):
            return jsonify({"error": "Invalid file type"}), 400

        filename = secure_filename(file.filename)
        unique_name = f"{uuid.uuid4().hex}_{filename}"
        save_path = os.path.join(app.config["UPLOAD_FOLDER"], unique_name)
        file.save(save_path)

        # store relative path in DB
        image_url = f"/uploads/{unique_name}"

    recipe = Recipe(
        title=title,
        category=category,
        prepTime=prep_time,
        image=image_url,           # <-- will be /uploads/... if file uploaded
        ingredients=ingredients,
        steps=steps,
        likes=likes,
        author=author,
        rating=rating,
    )

    db.session.add(recipe)
    db.session.commit()

    return jsonify({
        "status": "ok",
        "recipe": {
            "id": recipe.id,
            "title": recipe.title,
            "image": recipe.image or ""
        }
    }), 201


@app.route("/recipes/<int:rid>", methods=["PUT"])
def edit_recipe(rid):
    recipe = Recipe.query.get(rid)
    if not recipe:
        return jsonify({"error": "Recipe not found"}), 404

    data = request.get_json(silent=True) or {}

    # allow partial update
    if "title" in data:
        recipe.title = (data.get("title") or "").strip() or recipe.title
    if "category" in data:
        recipe.category = (data.get("category") or "").strip()
    if "prepTime" in data:
        try:
            recipe.prepTime = int(data.get("prepTime") or 0)
        except:
            pass
    if "image" in data:
        recipe.image = (data.get("image") or "").strip()
    if "ingredients" in data:
        recipe.ingredients = parse_list_field(data.get("ingredients"))
    if "steps" in data:
        recipe.steps = parse_list_field(data.get("steps"))
    if "rating" in data:
        try:
            recipe.rating = int(data.get("rating") or 0)
        except:
            recipe.rating = 0

    db.session.commit()
    return jsonify({"status": "updated"})


@app.route("/recipes/<int:rid>", methods=["DELETE"])
def delete_recipe(rid):
    recipe = Recipe.query.get(rid)
    if not recipe:
        return jsonify({"error": "Recipe not found"}), 404

    # optional: delete uploaded file from disk if it was an upload
    if recipe.image and recipe.image.startswith("/uploads/"):
        filename = recipe.image.replace("/uploads/", "", 1)
        path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        if os.path.exists(path):
            try:
                os.remove(path)
            except:
                pass

    db.session.delete(recipe)
    db.session.commit()
    return jsonify({"status": "deleted"})


@app.route("/recipes/<int:rid>/like", methods=["POST"])
def like_recipe(rid):
    data = request.json or {}
    username = data.get("username")

    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    recipe = Recipe.query.get(rid)
    if not recipe:
        return jsonify({"error": "Recipe not found"}), 404

    # Check if this user already liked it
    existing_like = Like.query.filter_by(user_id=user.id, recipe_id=recipe.id).first()

    if existing_like:
        # Unlike (remove)
        db.session.delete(existing_like)
        recipe.likes = max(0, recipe.likes - 1)
        action = "unliked"
    else:
        # Like
        new_like = Like(user_id=user.id, recipe_id=recipe.id)
        db.session.add(new_like)
        recipe.likes += 1
        action = "liked"

    db.session.commit()
    return jsonify({"status": action, "likes": recipe.likes})



# ---------------- Comments ------------------------
@app.route("/comments/<int:recipe_id>", methods=["GET"])
def get_comments(recipe_id):
    comments = Comment.query.filter_by(recipe_id=recipe_id).all()
    out = []
    for c in comments:
        u = User.query.get(c.user_id)
        out.append({
            "id": c.id,
            "user": u.username if u else "Unknown",
            "content": c.content or ""
        })
    return jsonify(out)


@app.route("/comments/<int:recipe_id>", methods=["POST"])
def add_comment(recipe_id):
    data = request.get_json(silent=True) or {}
    if not data.get("user_id") or not data.get("content"):
        return jsonify({"error": "Missing fields"}), 400

    comment = Comment(
        user_id=int(data["user_id"]),
        recipe_id=recipe_id,
        content=str(data["content"])
    )
    db.session.add(comment)
    db.session.commit()
    return jsonify({"status": "ok"})


# ---------------- Users --------------------------
@app.route("/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = (data.get("password") or "").strip()

    if not username or not password:
        return jsonify({"error": "username and password required"}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({"error": "User exists"}), 400

    user = User(
        username=username,
        password=password,
        role=(data.get("role") or "user")
    )
    db.session.add(user)
    db.session.commit()

    return jsonify({
        "status": "registered",
        "user": {"id": user.id, "username": user.username, "role": user.role}
    })


@app.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = (data.get("password") or "").strip()

    user = User.query.filter_by(username=username, password=password).first()
    if not user:
        return jsonify({"error": "Invalid credentials"}), 401

    return jsonify({
        "status": "ok",
        "user": {"id": user.id, "username": user.username, "role": user.role}
    })


# ---------------- Init DB ------------------------
def init_db():
    with app.app_context():
        ensure_upload_folder()
        db.create_all()


# ---------------- Run ----------------------------
if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)
