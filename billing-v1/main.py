# billing service
# NOTE: amounts kept in paise internally (int). api speaks rupees.
import os, sqlite3, json, datetime
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional

DB = os.environ.get("BILLING_DB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "billing.db"))
HOME = "Maharashtra"
LF = 2  # late fee pct

app = FastAPI(title="Billing")

CUST = [
    ("Asha Patil", "Maharashtra"), ("Rohan Deshmukh", "Maharashtra"),
    ("Kavya Rao", "Karnataka"), ("Nikhil Gowda", "Karnataka"),
    ("Anjali Nair", "Kerala"), ("Joseph Thomas", "Kerala"),
    ("Priya Sharma", "Delhi"), ("Vikram Malhotra", "Delhi"),
    ("Meena Iyer", "Tamil Nadu"), ("Arjun Raman", "Tamil Nadu"),
]
PROD = [
    ("SKU-TEA", "Assam tea 500g", 240, 5), ("SKU-RICE", "Basmati rice 5kg", 650, 5),
    ("SKU-OIL", "Groundnut oil 1L", 180, 5), ("SKU-SOAP", "Sandal soap", 45, 18),
    ("SKU-PEN", "Gel pen pack", 120, 12), ("SKU-BOOK", "Notebook A4", 85, 12),
    ("SKU-BAG", "Laptop bag", 1499, 18), ("SKU-MOUSE", "Wireless mouse", 799, 18),
    ("SKU-CABLE", "USB-C cable", 99.99, 18), ("SKU-LAMP", "Desk lamp", 1250, 12),
    ("SKU-GHEE", "Desi ghee 1L", 620, 12), ("SKU-SHOE", "Running shoes", 2999, 18),
    ("SKU-TOWEL", "Bath towel", 349.50, 12), ("SKU-CHARGER", "Phone charger", 149.99, 18),
    ("SKU-SPICE", "Garam masala", 19.99, 5),
]


def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def p(x):  # rupees -> paise
    return int(round(float(x) * 100))


def r(x):  # paise -> rupees
    return round(x / 100.0, 2)


def hu(n, d):  # n/d rounded half up, ints only
    q, m = divmod(n, d)
    return q + 1 if m * 2 >= d else q


def init():
    c = db()
    c.executescript("""
    drop table if exists cust; drop table if exists prod; drop table if exists inv;
    drop table if exists li; drop table if exists rf;
    create table cust(id integer primary key, nm text, st text);
    create table prod(sku text primary key, nm text, pr integer, gr integer);
    create table inv(id integer primary key, cid integer, st text, cp integer, dd text,
      sub integer, tx integer, dsc integer, tot integer, status text, lf integer, paid integer,
      pon text, rfd integer, cat text);
    create table li(id integer primary key, iid integer, sku text, q integer, up integer, gr integer);
    create table rf(id integer primary key, iid integer, sku text, q integer, amt integer, tx integer, cat text);
    """)
    for n, s in CUST:
        c.execute("insert into cust(nm,st) values(?,?)", (n, s))
    for s, n, pr, g in PROD:
        c.execute("insert into prod values(?,?,?,?)", (s, n, p(pr), g))
    c.commit(); c.close()


def now():
    return datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"


def calc(lines, cp):
    # lines: [(q, up_paise, gr)]
    sub = sum(q * up for q, up, g in lines)
    raw = sum(q * up * g for q, up, g in lines)  # tax * 100
    tx = hu(raw, 100)
    dsc = hu((sub + tx) * cp, 100) if cp else 0
    return sub, tx, dsc, sub + tx - dsc


def split(tx, inter):
    if inter:
        return 0, 0, tx
    a = hu(tx, 2)
    return a, tx - a, 0


def out(c, iid):
    i = c.execute("select * from inv where id=?", (iid,)).fetchone()
    if not i:
        raise HTTPException(404, "invoice not found")
    ls = c.execute("select * from li where iid=? order by id", (iid,)).fetchall()
    rs = c.execute("select * from rf where iid=? order by id", (iid,)).fetchall()
    inter = i["st"] != HOME
    cg, sg, ig = split(i["tx"], inter)
    return {
        "id": i["id"], "customer_id": i["cid"], "state": i["st"], "interstate": inter,
        "items": [{"sku": l["sku"], "qty": l["q"], "unit_price": r(l["up"]), "gst_rate": l["gr"],
                   "amount": r(l["q"] * l["up"])} for l in ls],
        "subtotal": r(i["sub"]), "cgst": r(cg), "sgst": r(sg), "igst": r(ig), "tax_total": r(i["tx"]),
        "coupon_pct": i["cp"], "discount": r(i["dsc"]), "total": r(i["tot"]),
        "due_date": i["dd"], "status": i["status"], "late_fee": r(i["lf"]),
        "amount_paid": r(i["paid"]), "paid_on": i["pon"], "refunded": r(i["rfd"]),
        "refunds": [{"id": x["id"], "sku": x["sku"], "qty": x["q"], "amount": r(x["amt"]),
                     "tax": r(x["tx"]), "created_at": x["cat"]} for x in rs],
        "created_at": i["cat"],
    }


class CIn(BaseModel):
    name: str
    state: str


class It(BaseModel):
    sku: str
    qty: int
    unit_price: Optional[float] = None
    gst_rate: Optional[int] = None


class IIn(BaseModel):
    customer_id: int
    items: List[It]
    coupon_pct: Optional[float] = 0
    due_date: str


class PIn(BaseModel):
    paid_on: str


class RIn(BaseModel):
    sku: str
    qty: int


@app.on_event("startup")
def _s():
    if not os.path.exists(DB):
        init()


@app.get("/health")
def health():
    return {"ok": True, "service": "billing-v1"}


@app.post("/reset")
def reset():
    init()
    return {"ok": True, "customers": len(CUST), "products": len(PROD)}


@app.post("/customers")
def mk_cust(b: CIn):
    c = db()
    cur = c.execute("insert into cust(nm,st) values(?,?)", (b.name, b.state))
    c.commit()
    k = cur.lastrowid
    c.close()
    return {"id": k, "name": b.name, "state": b.state}


@app.post("/invoices")
def mk_inv(b: IIn):
    c = db()
    cu = c.execute("select * from cust where id=?", (b.customer_id,)).fetchone()
    if not cu:
        raise HTTPException(404, "customer not found")
    if not b.items:
        raise HTTPException(400, "no items")
    try:
        datetime.date.fromisoformat(b.due_date)
    except ValueError:
        raise HTTPException(400, "bad due_date")
    ls = []
    for it in b.items:
        pr = c.execute("select * from prod where sku=?", (it.sku,)).fetchone()
        up = p(it.unit_price) if it.unit_price is not None else (pr["pr"] if pr else None)
        g = it.gst_rate if it.gst_rate is not None else (pr["gr"] if pr else None)
        if up is None or g is None:
            raise HTTPException(400, "unknown sku " + it.sku)
        if g not in (5, 12, 18):
            raise HTTPException(400, "bad gst_rate")
        if it.qty <= 0:
            raise HTTPException(400, "bad qty")
        ls.append((it.sku, it.qty, up, g))
    cp = int(b.coupon_pct or 0)
    sub, tx, dsc, tot = calc([(q, up, g) for s, q, up, g in ls], cp)
    cur = c.execute("insert into inv(cid,st,cp,dd,sub,tx,dsc,tot,status,lf,paid,pon,rfd,cat) "
                    "values(?,?,?,?,?,?,?,?,'open',0,0,null,0,?)",
                    (cu["id"], cu["st"], cp, b.due_date, sub, tx, dsc, tot, now()))
    iid = cur.lastrowid
    for s, q, up, g in ls:
        c.execute("insert into li(iid,sku,q,up,gr) values(?,?,?,?,?)", (iid, s, q, up, g))
    c.commit()
    o = out(c, iid)
    c.close()
    return o


@app.get("/invoices/{iid}")
def get_inv(iid: int):
    c = db()
    o = out(c, iid)
    c.close()
    return o


@app.post("/invoices/{iid}/pay")
def pay(iid: int, b: PIn):
    c = db()
    i = c.execute("select * from inv where id=?", (iid,)).fetchone()
    if not i:
        raise HTTPException(404, "invoice not found")
    if i["status"] != "open":
        raise HTTPException(400, "invoice not open")
    try:
        po = datetime.date.fromisoformat(b.paid_on)
    except ValueError:
        raise HTTPException(400, "bad paid_on")
    dd = datetime.date.fromisoformat(i["dd"])
    lf = 0
    if po > dd and dd.weekday() != 6:
        lf = hu(i["tot"] * LF, 100)
    c.execute("update inv set status='paid', lf=?, paid=?, pon=? where id=?",
              (lf, i["tot"] + lf, b.paid_on, iid))
    c.commit()
    o = out(c, iid)
    c.close()
    return o


@app.post("/invoices/{iid}/refund")
def refund(iid: int, b: RIn):
    c = db()
    i = c.execute("select * from inv where id=?", (iid,)).fetchone()
    if not i:
        raise HTTPException(404, "invoice not found")
    l = c.execute("select * from li where iid=? and sku=?", (iid, b.sku)).fetchone()
    if not l:
        raise HTTPException(400, "sku not on invoice")
    done = c.execute("select coalesce(sum(q),0) from rf where iid=? and sku=?", (iid, b.sku)).fetchone()[0]
    if b.qty <= 0 or b.qty + done > l["q"]:
        raise HTTPException(400, "bad refund qty")
    base = b.qty * l["up"]
    tx = hu(base * l["gr"], 100)
    amt = base + tx
    if i["cp"]:
        amt = amt - hu(amt * i["cp"], 100)
    c.execute("insert into rf(iid,sku,q,amt,tx,cat) values(?,?,?,?,?,?)", (iid, b.sku, b.qty, amt, tx, now()))
    c.execute("update inv set rfd=rfd+? where id=?", (amt, iid))
    c.commit()
    o = out(c, iid)
    c.close()
    return o
