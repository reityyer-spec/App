
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_from_directory
import sqlite3, os, uuid
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "hoshi-v031-demo-secret-change-me")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# RailwayでVolumeを使う場合は HOSHI_DATA_DIR=/data を設定するとDBと画像を永続化できます。
DATA_DIR = os.environ.get("HOSHI_DATA_DIR", BASE_DIR)
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "hoshi.db")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    con = db()
    con.executescript("""
    PRAGMA foreign_keys = ON;

    CREATE TABLE IF NOT EXISTS users(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      username TEXT UNIQUE NOT NULL,
      display_name TEXT NOT NULL,
      verified INTEGER NOT NULL DEFAULT 1,
      rating REAL NOT NULL DEFAULT 5.0,
      success_rate INTEGER NOT NULL DEFAULT 100,
      balance INTEGER NOT NULL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS posts(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL,
      post_type TEXT NOT NULL CHECK(post_type IN ('request','offer')),
      title TEXT NOT NULL,
      body TEXT NOT NULL,
      location TEXT,
      target_date TEXT,
      proxy_fee INTEGER NOT NULL DEFAULT 0,
      product_price INTEGER NOT NULL DEFAULT 0,
      status TEXT NOT NULL DEFAULT '募集中',
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY(user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS likes(
      user_id INTEGER NOT NULL,
      post_id INTEGER NOT NULL,
      PRIMARY KEY(user_id, post_id)
    );

    CREATE TABLE IF NOT EXISTS comments(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      post_id INTEGER NOT NULL,
      user_id INTEGER NOT NULL,
      body TEXT NOT NULL,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS follows(
      follower_id INTEGER NOT NULL,
      followee_id INTEGER NOT NULL,
      PRIMARY KEY(follower_id, followee_id)
    );

    CREATE TABLE IF NOT EXISTS applications(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      post_id INTEGER NOT NULL,
      applicant_id INTEGER NOT NULL,
      fee_offer INTEGER NOT NULL,
      message TEXT,
      status TEXT NOT NULL DEFAULT '応募中',
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS transactions(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      post_id INTEGER NOT NULL,
      requester_id INTEGER NOT NULL,
      agent_id INTEGER NOT NULL,
      product_price INTEGER NOT NULL,
      proxy_fee INTEGER NOT NULL,
      platform_fee INTEGER NOT NULL,
      shipping_estimate INTEGER NOT NULL DEFAULT 700,
      status TEXT NOT NULL DEFAULT '商品購入待ち',
      receipt_attached INTEGER NOT NULL DEFAULT 0,
      item_photos_attached INTEGER NOT NULL DEFAULT 0,
      delivery_code TEXT,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS messages(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      transaction_id INTEGER NOT NULL,
      user_id INTEGER NOT NULL,
      body TEXT NOT NULL,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS proofs(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      transaction_id INTEGER NOT NULL,
      user_id INTEGER NOT NULL,
      kind TEXT NOT NULL,
      filename TEXT NOT NULL,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS reviews(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      transaction_id INTEGER NOT NULL,
      reviewer_id INTEGER NOT NULL,
      reviewee_id INTEGER NOT NULL,
      stars INTEGER NOT NULL,
      comment TEXT
    );
    """)

    if con.execute("SELECT COUNT(*) c FROM users").fetchone()["c"] == 0:
        con.executemany("INSERT INTO users(username,display_name,verified,rating,success_rate,balance) VALUES(?,?,?,?,?,?)", [
            ("yuna__", "Yuna", 1, 4.98, 99, 12800),
            ("miki___", "Miki", 1, 4.96, 98, 23400),
            ("rina_tokyo", "Rina", 1, 5.00, 100, 8600),
        ])
        con.commit()

    if con.execute("SELECT COUNT(*) c FROM posts").fetchone()["c"] == 0:
        users = {r["username"]: r["id"] for r in con.execute("SELECT id,username FROM users")}
        con.executemany("""INSERT INTO posts(user_id,post_type,title,body,location,target_date,proxy_fee,product_price)
                          VALUES(?,?,?,?,?,?,?,?)""", [
            (users["yuna__"], "request", "andwang POPUP 代行お願い", "限定トップスを購入してくださる方を探しています♡", "東京・渋谷", "9/11", 2000, 15000),
            (users["miki___"], "offer", "表参道・銀座 代行できます", "午後から回れます。購入証明・発送前写真対応◎", "東京", "9/12", 1800, 0),
            (users["rina_tokyo"], "offer", "韓国ブランドPOPUP行きます", "ファッション・コスメ中心に対応できます☆", "新宿", "9/14", 2500, 0),
        ])
        con.commit()

    if con.execute("SELECT COUNT(*) c FROM transactions").fetchone()["c"] == 0:
        users = {r["username"]: r["id"] for r in con.execute("SELECT id,username FROM users")}
        post_id = con.execute("SELECT id FROM posts WHERE post_type='request' ORDER BY id LIMIT 1").fetchone()["id"]
        pf = round(2000 * 0.055)
        con.execute("""INSERT INTO transactions(post_id,requester_id,agent_id,product_price,proxy_fee,platform_fee,status,receipt_attached,item_photos_attached,delivery_code)
                       VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (post_id, users["yuna__"], users["miki___"], 89000, 2000, pf, "商品購入済み", 1, 1, "482913"))
        txid = con.execute("SELECT last_insert_rowid() id").fetchone()["id"]
        con.executemany("INSERT INTO messages(transaction_id,user_id,body) VALUES(?,?,?)", [
            (txid, users["miki___"], "購入できました！レシートと商品写真を添付しました。"),
            (txid, users["yuna__"], "確認しました♡ 発送をお願いします。"),
        ])
        con.commit()

    con.close()

@app.before_request
def ensure_user():
    if 'user_id' not in session:
        session['user_id'] = 1

def current_user():
    con = db()
    u = con.execute("SELECT * FROM users WHERE id=?", (session.get('user_id',1),)).fetchone()
    con.close()
    return u

@app.route("/")
def home():
    con = db()
    tab = request.args.get("tab","recommended")
    if tab == "following":
        rows = con.execute("""
          SELECT p.*,u.username,u.rating,u.verified,
                 (SELECT COUNT(*) FROM likes l WHERE l.post_id=p.id) likes_count,
                 (SELECT COUNT(*) FROM comments c WHERE c.post_id=p.id) comments_count
          FROM posts p JOIN users u ON u.id=p.user_id
          WHERE p.user_id IN (SELECT followee_id FROM follows WHERE follower_id=?)
          ORDER BY p.id DESC
        """,(session['user_id'],)).fetchall()
    else:
        rows = con.execute("""
          SELECT p.*,u.username,u.rating,u.verified,
                 (SELECT COUNT(*) FROM likes l WHERE l.post_id=p.id) likes_count,
                 (SELECT COUNT(*) FROM comments c WHERE c.post_id=p.id) comments_count
          FROM posts p JOIN users u ON u.id=p.user_id
          ORDER BY p.id DESC
        """).fetchall()
    con.close()
    return render_template("index.html", view="home", posts=rows, user=current_user(), tab=tab)

@app.route("/search")
def search():
    q = request.args.get("q","").strip()
    con = db()
    if q:
        rows = con.execute("""
          SELECT p.*,u.username,u.rating,
                 (SELECT COUNT(*) FROM likes l WHERE l.post_id=p.id) likes_count,
                 (SELECT COUNT(*) FROM comments c WHERE c.post_id=p.id) comments_count
          FROM posts p JOIN users u ON u.id=p.user_id
          WHERE p.title LIKE ? OR p.body LIKE ? OR p.location LIKE ?
          ORDER BY p.id DESC
        """, tuple(["%"+q+"%"]*3)).fetchall()
    else:
        rows = []
    con.close()
    return render_template("index.html", view="search", posts=rows, user=current_user(), q=q)

@app.route("/post/new", methods=["GET","POST"])
def new_post():
    if request.method == "POST":
        con = db()
        con.execute("""INSERT INTO posts(user_id,post_type,title,body,location,target_date,proxy_fee,product_price)
                       VALUES(?,?,?,?,?,?,?,?)""",(
            session['user_id'], request.form['post_type'], request.form['title'], request.form['body'],
            request.form.get('location',''), request.form.get('target_date',''),
            int(request.form.get('proxy_fee') or 0), int(request.form.get('product_price') or 0)
        ))
        con.commit(); con.close()
        return redirect(url_for("home"))
    return render_template("index.html", view="new_post", user=current_user())

@app.route("/post/<int:post_id>")
def post_detail(post_id):
    con = db()
    post = con.execute("""
      SELECT p.*,u.username,u.rating,u.success_rate,
             (SELECT COUNT(*) FROM likes l WHERE l.post_id=p.id) likes_count
      FROM posts p JOIN users u ON u.id=p.user_id WHERE p.id=?
    """,(post_id,)).fetchone()
    comments = con.execute("""
      SELECT c.*,u.username FROM comments c JOIN users u ON u.id=c.user_id
      WHERE c.post_id=? ORDER BY c.id
    """,(post_id,)).fetchall()
    apps = con.execute("""
      SELECT a.*,u.username,u.rating,u.success_rate FROM applications a
      JOIN users u ON u.id=a.applicant_id WHERE a.post_id=? ORDER BY a.id DESC
    """,(post_id,)).fetchall()
    con.close()
    return render_template("index.html", view="detail", post=post, comments=comments, applications=apps, user=current_user())

@app.post("/post/<int:post_id>/like")
def like(post_id):
    con=db()
    hit=con.execute("SELECT 1 FROM likes WHERE user_id=? AND post_id=?",(session['user_id'],post_id)).fetchone()
    if hit:
        con.execute("DELETE FROM likes WHERE user_id=? AND post_id=?",(session['user_id'],post_id))
    else:
        con.execute("INSERT INTO likes(user_id,post_id) VALUES(?,?)",(session['user_id'],post_id))
    con.commit(); con.close()
    return redirect(request.referrer or url_for("home"))

@app.post("/post/<int:post_id>/comment")
def comment(post_id):
    body=request.form.get("body","").strip()
    if body:
        con=db(); con.execute("INSERT INTO comments(post_id,user_id,body) VALUES(?,?,?)",(post_id,session['user_id'],body)); con.commit(); con.close()
    return redirect(url_for("post_detail",post_id=post_id))

@app.post("/post/<int:post_id>/apply")
def apply(post_id):
    con=db()
    con.execute("INSERT INTO applications(post_id,applicant_id,fee_offer,message) VALUES(?,?,?,?)",(
        post_id,session['user_id'],int(request.form.get("fee_offer") or 0),request.form.get("message","")
    ))
    con.commit(); con.close()
    return redirect(url_for("post_detail",post_id=post_id))

@app.route("/transactions")
def transactions_list():
    con=db()
    rows=con.execute("""
      SELECT t.*,p.title,ru.username requester_name,au.username agent_name
      FROM transactions t
      JOIN posts p ON p.id=t.post_id
      JOIN users ru ON ru.id=t.requester_id
      JOIN users au ON au.id=t.agent_id
      WHERE t.requester_id=? OR t.agent_id=?
      ORDER BY t.id DESC
    """,(session['user_id'],session['user_id'])).fetchall()
    con.close()
    return render_template("index.html", view="transactions", transactions=rows, user=current_user())

@app.route("/chat/<int:txid>")
def chat(txid):
    con=db()
    tx=con.execute("""
      SELECT t.*,p.title,ru.username requester_name,au.username agent_name
      FROM transactions t
      JOIN posts p ON p.id=t.post_id
      JOIN users ru ON ru.id=t.requester_id
      JOIN users au ON au.id=t.agent_id
      WHERE t.id=?
    """,(txid,)).fetchone()
    msgs=con.execute("""
      SELECT m.*,u.username FROM messages m JOIN users u ON u.id=m.user_id
      WHERE m.transaction_id=? ORDER BY m.id
    """,(txid,)).fetchall()
    con.close()
    return render_template("index.html", view="chat", tx=tx, messages=msgs, user=current_user())

@app.route("/transaction/<int:txid>")
def transaction(txid):
    role=request.args.get("role","requester")
    con=db()
    tx=con.execute("""
      SELECT t.*,p.title, ru.username requester_name, au.username agent_name
      FROM transactions t
      JOIN posts p ON p.id=t.post_id
      JOIN users ru ON ru.id=t.requester_id
      JOIN users au ON au.id=t.agent_id
      WHERE t.id=?
    """,(txid,)).fetchone()
    msgs=con.execute("""
      SELECT m.*,u.username FROM messages m JOIN users u ON u.id=m.user_id
      WHERE m.transaction_id=? ORDER BY m.id
    """,(txid,)).fetchall()
    proofs=con.execute("SELECT * FROM proofs WHERE transaction_id=? ORDER BY id DESC",(txid,)).fetchall()
    con.close()
    return render_template("index.html", view="transaction", tx=tx, messages=msgs, proofs=proofs, role=role, user=current_user())

@app.post("/transaction/<int:txid>/message")
def send_message(txid):
    body=request.form.get("body","").strip()
    if body:
        con=db(); con.execute("INSERT INTO messages(transaction_id,user_id,body) VALUES(?,?,?)",(txid,session['user_id'],body)); con.commit(); con.close()
    return redirect(request.referrer or url_for("transaction",txid=txid))

@app.post("/transaction/<int:txid>/upload")
def upload_proof(txid):
    f=request.files.get("file")
    kind=request.form.get("kind","item_photo")
    if f and f.filename:
        name=f"{uuid.uuid4().hex}_{secure_filename(f.filename)}"
        f.save(os.path.join(UPLOAD_DIR,name))
        con=db()
        con.execute("INSERT INTO proofs(transaction_id,user_id,kind,filename) VALUES(?,?,?,?)",(txid,session['user_id'],kind,name))
        if kind=="receipt":
            con.execute("UPDATE transactions SET receipt_attached=1 WHERE id=?",(txid,))
        if kind=="item_photo":
            con.execute("UPDATE transactions SET item_photos_attached=1 WHERE id=?",(txid,))
        con.commit(); con.close()
    return redirect(request.referrer or url_for("transaction",txid=txid))

@app.route("/uploads/<path:name>")
def uploads(name):
    return send_from_directory(UPLOAD_DIR,name)

@app.route("/profile")
def profile():
    con=db()
    u=con.execute("SELECT * FROM users WHERE id=?",(session['user_id'],)).fetchone()
    myposts=con.execute("SELECT * FROM posts WHERE user_id=? ORDER BY id DESC",(session['user_id'],)).fetchall()
    con.close()
    return render_template("index.html",view="profile",user=u,myposts=myposts)

@app.route("/switch/<int:uid>")
def switch(uid):
    con=db()
    if con.execute("SELECT 1 FROM users WHERE id=?",(uid,)).fetchone():
        session['user_id']=uid
    con.close()
    return redirect(request.referrer or url_for("home"))

@app.get("/health")
def health():
    return jsonify({"ok": True, "app": "HOSHI", "version": "0.3.2"})

@app.get("/api/posts")
def api_posts():
    con=db()
    rows=[dict(r) for r in con.execute("SELECT * FROM posts ORDER BY id DESC").fetchall()]
    con.close()
    return jsonify(rows)

# Gunicorn / Railway起動時にもDBを自動初期化
init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
