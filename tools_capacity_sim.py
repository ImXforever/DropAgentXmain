#!/usr/bin/env python3
# ═══════════════════════════════════════════════════════════════════
# شبیه‌ساز ظرفیت v3.3.3 — اسکیمای کامل مونوریپو (پایه + جداول v3)
# چت ۲۵×(2000/1500) · FTS کاربر · فایل ابری · app_logs با ریتین ۱۴روز/۵۰k
# memory_facets با TTL · rl_identity · هدف: 8000 کاربر زیر 500MB
# ═══════════════════════════════════════════════════════════════════
import os, re, sqlite3, random, time, json

random.seed(333)
DB = "/tmp/sim_v333.db"
LIMIT = 500 * 1024 * 1024; WARN = 400 * 1024 * 1024
SRC = open("/home/user/bot-v333/database.py", encoding="utf-8").read()
for mod in ("memory2.py", "observability.py", "identity_rl.py"):
    SRC += open("/home/user/bot-v333/" + mod, encoding="utf-8").read()

def fresh_db():
    for f in (DB, DB+"-wal", DB+"-shm"):
        if os.path.exists(f): os.remove(f)
    con = sqlite3.connect(DB)
    con.execute("PRAGMA journal_mode=WAL"); con.execute("PRAGMA synchronous=NORMAL")
    for m in re.finditer(r'CREATE TABLE IF NOT EXISTS (\w+)\s*\((.*?)\n\s*\)', SRC, re.S):
        try: con.execute(m.group(0))
        except Exception: pass
    for m in re.finditer(r'"(CREATE INDEX IF NOT EXISTS [^"]+)"', SRC):
        try: con.execute(m.group(1))
        except Exception: pass
    for m in re.finditer(r'"(ALTER TABLE [^"]+)"', SRC):
        try: con.execute(m.group(1))
        except Exception: pass
    con.execute("CREATE VIRTUAL TABLE IF NOT EXISTS chat_fts USING fts5(content, user_id UNINDEXED, msg_id UNINDEXED, session_id UNINDEXED)")
    return con

WORDS = ["سلام","ایجنت","محصول","قیمت","دانلود","بات","فروش","کد","قالب","آموزش",
         "پرداخت","اعتبار","فایل","توضیح","مرسی","کیفیت","پیشنهاد","راهنما","درست","بله"]
def fa(rng, n): return " ".join(rng.choice(WORDS) for _ in range(n))
KEEP, UCAP, ACAP = 25, 2000, 1500
FACETS = ["identity","factual","preference","behavioral","emotional","engagement","risk"]

def populate(con, n, heavy):
    rng = random.Random(n * 31 + (7 if heavy else 0))
    shares = ([("dormant",.15),("casual",.35),("active",.35),("power",.15)] if heavy
              else [("dormant",.55),("casual",.30),("active",.12),("power",.03)])
    start = 1
    for cname, share in shares:
        k = int(n * share)
        for uid in range(start, start + k):
            con.execute("INSERT INTO users (user_id, username, first_name, credits, total_earned, created_at) VALUES (?,?,?,?,?,?)",
                        (uid, f"u{uid}", fa(rng,2), rng.randint(0,800), rng.randint(0,3000), time.time()-rng.randint(0,86400*300)))
            con.execute("INSERT OR IGNORE INTO user_profile (user_id, interests, persona, updated_at) VALUES (?,?,?,?)",
                        (uid, fa(rng,4), fa(rng,8), time.time()))
            con.execute("INSERT OR REPLACE INTO hermes_sessions (user_id, session_id, updated_at) VALUES (?,?,?)",
                        (uid, rng.randint(1,10**6), time.time()))
            con.execute("INSERT OR REPLACE INTO rl_identity (user_id, label, qvalues, updated_at) VALUES (?,?,?,?)",
                        (uid, rng.choice(["new_user","browser","task_earner","returning_buyer","high_value"]), "{}", time.time()))
            lvl = {"dormant":(2,3,0,1,1,2),"casual":(12,30,3,4,6,6),"active":(45,KEEP,8,10,14,10),"power":(120,KEEP,18,22,24,14)}[cname]
            n_tx, n_chat, n_sess, n_purch, n_mem, n_facets = lvl
            a_avg = {"dormant":400,"casual":800,"active":1100,"power":1450}[cname] if heavy else \
                    {"dormant":350,"casual":650,"active":850,"power":1100}[cname]
            for _ in range(rng.randint(n_tx//2, n_tx)):
                con.execute("INSERT INTO transactions (user_id, amount, tx_type, description, created_at) VALUES (?,?,?,?,?)",
                            (uid, rng.randint(-500,500), "purchase", fa(rng,3), time.time()-rng.randint(0,86400*180)))
            for _ in range(rng.randint(max(1,n_purch//2), n_purch)):
                con.execute("INSERT INTO purchases (buyer_id, product_id, price_credits) VALUES (?,?,?)",
                            (uid, rng.randint(1,1000), rng.randint(20,400)))
            nc = min(n_chat + rng.randint(-2,0), KEEP)
            for i in range(max(0, nc)):
                role = "user" if i%2==0 else "assistant"
                content = (fa(rng, rng.randint(8,130))[:UCAP] if role=="user"
                           else fa(rng, int(rng.uniform(a_avg*.7, min(a_avg*1.3, ACAP))/5.5))[:ACAP])
                cur = con.execute("INSERT INTO chat_messages (user_id, role, content) VALUES (?,?,?)", (uid, role, content))
                if role == "user":
                    con.execute("INSERT INTO chat_fts (content, user_id, msg_id) VALUES (?,?,?)", (content, uid, cur.lastrowid))
            for _ in range(rng.randint(n_sess//2 if n_sess>1 else n_sess, n_sess)):
                con.execute("INSERT INTO sessions (user_id, title, created_at) VALUES (?,?,?)", (uid, fa(rng,3), time.time()))
            for _ in range(rng.randint(n_mem//2 if n_mem>1 else n_mem, n_mem)):
                con.execute("INSERT INTO user_memories (user_id, kind, content, dedup_key, created_at) VALUES (?,?,?,?,?)",
                            (uid, "fact", fa(rng, rng.randint(8,25)), f"d{uid}_{_}", time.time()))
            # memory_facets (v3) — sticky identity همیشه، بقیه TTL-دار؛ میانگین واقع‌بینانه
            n_f = rng.randint(1, n_facets)
            for j in range(n_f):
                con.execute("INSERT INTO memory_facets (user_id, facet, content, importance, dedup_key, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
                            (uid, "identity" if j==0 else rng.choice(FACETS), fa(rng, rng.randint(6,20)), rng.uniform(1,5), f"f{uid}_{j}", time.time(), time.time()))
            if rng.random() < .1:
                con.execute("INSERT INTO follows (follower_id, target_id, created_at) VALUES (?,?,?)", (uid, rng.randint(1,n), time.time()))
            if uid % 200 == 0:
                con.commit(); con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        start += k
        con.commit(); con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    for c in range(max(1, n//8)):
        for p in range(2):
            con.execute("INSERT INTO products (creator_id, title, description, price_credits, file_path, file_fileid, category, created_at) VALUES (?,?,?,?,?,?,?,?)",
                        (rng.randint(1,n), fa(rng,4), fa(rng,130), rng.randint(20,400), None if rng.random()<.8 else "uploads/x.pdf", "AgAC-fid", "coding", time.time()))
    # app_logs — حالت پایای ریتین: سقف 50k ردیف (۱۴روز)
    for i in range(50000):
        con.execute("INSERT INTO app_logs (ts, level, logger, msg, data, user_id) VALUES (?,?,?,?,?,?)",
                    (time.time()-rng.randint(0,14*86400), rng.choice(["INFO","WARNING","ERROR"]), "sim", fa(rng,6), "{}", rng.randint(1,n)))
    con.commit(); con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    size = os.path.getsize(DB)
    for ext in ("-wal","-shm"):
        if os.path.exists(DB+ext): size += os.path.getsize(DB+ext)
    return size

print("═══ شبیه‌سازی v3.3.3 (مونوریپو کامل + ریتین‌های جدید) ═══\n")
out = {}
for scen, heavy in (("realistic_v333", False), ("ai_heavy_v333", True)):
    pts = []
    for n in (4000, 8000):
        con = fresh_db(); size = populate(con, n, heavy); con.close()
        pts.append((n, size))
        m = "✅" if size < WARN else ("🟡" if size < LIMIT else "❌")
        print(f"  [{scen}] n={n:>5} → {size/1024/1024:7.1f} MB ({size/n/1024:.1f} KB/user) {m}")
    xs=[p[0] for p in pts]; ys=[p[1] for p in pts]
    b=(ys[1]-ys[0])/(xs[1]-xs[0]); a=ys[0]-b*xs[0]
    out[scen]=dict(per_user_kb=b/1024, max_users=int((LIMIT-a)/b), safe_users=int((WARN-a)/b))
    print(f"  ⇒ {b/1024:.1f} KB/یوزر (app_logs پایا ≈ {(a/1024/1024):.0f}MB ثابت) → سقف ≈ {int((LIMIT-a)/b):,} · امن ≈ {int((WARN-a)/b):,}\n")
json.dump(out, open("/tmp/capacity_v333.json","w"))
for f in (DB, DB+"-wal", DB+"-shm"):
    if os.path.exists(f): os.remove(f)
print("═══ پایان ═══")
