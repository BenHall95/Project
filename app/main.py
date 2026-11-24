import os
import uuid
import shutil
from datetime import date
from typing import Optional
from fastapi import FastAPI, Depends, HTTPException, Request, Form, File, UploadFile
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func
from . import models, crud, auth
from .database import engine, get_db, SessionLocal

UPLOAD_DIR = "static/uploads"
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
os.makedirs(UPLOAD_DIR, exist_ok=True)

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Прокат оборудования")
app.add_middleware(SessionMiddleware, secret_key="super-secret-rental-key-2026")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

def seed_data():
    db = SessionLocal()
    try:
        if not db.query(models.User).first():
            db.add_all([
                models.User(username="admin", hashed_password=auth.hash_password("admin"), role="admin"),
                models.User(username="manager", hashed_password=auth.hash_password("manager"), role="manager"),
                models.User(username="client", hashed_password=auth.hash_password("client"), role="client"),
            ])
        if not db.query(models.Equipment).first():
            db.add_all([
                models.Equipment(name="Горный велосипед Stern Motion", category="Спорт", price_per_day=1200, total_qty=5, broken_qty=0, image_url="/static/uploads/bik.jpg"),
                models.Equipment(name="Палатка туристическая 4-местная", category="Туризм", price_per_day=800, total_qty=4, broken_qty=0, image_url="/static/uploads/palatk.jpg"),
                models.Equipment(name="Перфоратор Bosch GBH 2-26", category="Стройка", price_per_day=950, total_qty=3, broken_qty=1, image_url="/static/uploads/perfrtr.jpg"),
                models.Equipment(name="Сапборд (SUP-доска) надувной", category="Спорт", price_per_day=1500, total_qty=6, broken_qty=0, image_url="/static/uploads/sup.jpg"),
            ])
        db.commit()
    finally:
        db.close()

seed_data()

@app.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    category: Optional[str] = None,
    search: Optional[str] = None,
    error: Optional[str] = None,
    success: Optional[str] = None,
    db: Session = Depends(get_db),
    user: Optional[models.User] = Depends(auth.get_current_user)
):
    query = db.query(models.Equipment)
    if category:
        query = query.filter(models.Equipment.category == category)
    if search:
        query = query.filter(models.Equipment.name.ilike(f"%{search}%"))
    items = query.all()
    categories = [r[0] for r in db.query(models.Equipment.category).distinct().all()]
    return templates.TemplateResponse("index.html", {
        "request": request,
        "items": items,
        "categories": categories,
        "selected_category": category or "",
        "search": search or "",
        "user": user,
        "error": error,
        "success": success,
        "today": date.today().isoformat()
    })

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, error: Optional[str] = None, user: Optional[models.User] = Depends(auth.get_current_user)):
    return templates.TemplateResponse("login.html", {"request": request, "error": error, "user": user})

@app.post("/login")
def login_action(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user or not auth.verify_password(password, user.hashed_password):
        return RedirectResponse(url="/login?error=Неверный+логин+или+пароль", status_code=303)
    request.session["user_id"] = user.id
    return RedirectResponse(url="/", status_code=303)

@app.post("/register")
def register_action(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    if db.query(models.User).filter(models.User.username == username).first():
        return RedirectResponse(url="/login?error=Пользователь+уже+существует", status_code=303)
    new_user = models.User(username=username, hashed_password=auth.hash_password(password), role="client")
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    request.session["user_id"] = new_user.id
    return RedirectResponse(url="/", status_code=303)

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=303)

@app.post("/book")
def book_equipment(
    request: Request,
    equipment_id: int = Form(...),
    quantity: int = Form(...),
    start_date: date = Form(...),
    end_date: date = Form(...),
    db: Session = Depends(get_db),
    user: Optional[models.User] = Depends(auth.get_current_user)
):
    if not user:
        return RedirectResponse(url="/login?error=Войдите+в+аккаунт+для+бронирования", status_code=303)
    try:
        crud.create_booking(db, user.id, equipment_id, start_date, end_date, quantity)
        return RedirectResponse(url="/profile?success=Бронирование+успешно+оформлено", status_code=303)
    except ValueError as e:
        return RedirectResponse(url=f"/?error={str(e)}", status_code=303)

@app.get("/profile", response_class=HTMLResponse)
def profile_page(
    request: Request,
    success: Optional[str] = None,
    db: Session = Depends(get_db),
    user: Optional[models.User] = Depends(auth.get_current_user)
):
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    today = date.today()
    bookings = db.query(models.Booking).filter(models.Booking.user_id == user.id).order_by(models.Booking.id.desc()).all()
    for b in bookings:
        if b.status == "issued" and b.end_date < today:
            b.status = "overdue"
    db.commit()
    return templates.TemplateResponse("profile.html", {
        "request": request,
        "user": user,
        "bookings": bookings,
        "success": success
    })

@app.get("/manager", response_class=HTMLResponse)
def manager_page(
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(auth.require_role(["manager", "admin"]))
):
    today = date.today()
    bookings = db.query(models.Booking).order_by(models.Booking.id.desc()).all()
    for b in bookings:
        if b.status == "issued" and b.end_date < today:
            b.status = "overdue"
    db.commit()
    return templates.TemplateResponse("manager.html", {
        "request": request,
        "user": user,
        "bookings": bookings
    })

@app.post("/manager/issue/{booking_id}")
def issue_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(auth.require_role(["manager", "admin"]))
):
    booking = db.query(models.Booking).filter(models.Booking.id == booking_id).first()
    if booking and booking.status == "booked":
        booking.status = "issued"
        db.commit()
    return RedirectResponse(url="/manager", status_code=303)

@app.post("/manager/return/{booking_id}")
def return_booking(
    booking_id: int,
    damage_fine: float = Form(0.0),
    broken_units: int = Form(0),
    note: str = Form("Без повреждений"),
    db: Session = Depends(get_db),
    user: models.User = Depends(auth.require_role(["manager", "admin"]))
):
    crud.return_equipment(db, booking_id, date.today(), damage_fine, broken_units, note)
    return RedirectResponse(url="/manager", status_code=303)

@app.get("/admin", response_class=HTMLResponse)
def admin_page(
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(auth.require_role(["admin"]))
):
    items = db.query(models.Equipment).all()
    users = db.query(models.User).all()
    
    cat_stats = (
        db.query(models.Equipment.category, func.coalesce(func.sum(models.Booking.total_price), 0))
        .outerjoin(models.Booking, models.Equipment.id == models.Booking.equipment_id)
        .group_by(models.Equipment.category)
        .all()
    )
    chart_labels = [c[0] for c in cat_stats]
    chart_values = [float(c[1]) for c in cat_stats]
    
    total_revenue = db.query(func.coalesce(func.sum(models.Booking.total_price), 0)).scalar()
    total_fines = db.query(func.coalesce(func.sum(models.Fine.amount), 0)).scalar()
    
    return templates.TemplateResponse("admin.html", {
        "request": request,
        "user": user,
        "items": items,
        "users": users,
        "chart_labels": chart_labels,
        "chart_values": chart_values,
        "total_revenue": total_revenue,
        "total_fines": total_fines
    })

@app.post("/admin/equipment/add")
async def add_equipment(
    name: str = Form(...),
    category: str = Form(...),
    price_per_day: float = Form(...),
    total_qty: int = Form(...),
    image: UploadFile = File(None),
    db: Session = Depends(get_db),
    user: models.User = Depends(auth.require_role(["admin"]))
):
    image_url = None
    if image and image.filename:
        ext = os.path.splitext(image.filename)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail="Недопустимый формат файла. Используйте PNG, JPG, JPEG или WEBP."
            )
        unique_filename = f"{uuid.uuid4().hex}{ext}"
        file_path = os.path.join(UPLOAD_DIR, unique_filename)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(image.file, buffer)
        image_url = f"/static/uploads/{unique_filename}"

    new_item = models.Equipment(
        name=name,
        category=category,
        price_per_day=price_per_day,
        total_qty=total_qty,
        image_url=image_url
    )
    db.add(new_item)
    db.commit()
    return RedirectResponse(url="/admin", status_code=303)

@app.post("/admin/equipment/update/{item_id}")
def update_equipment(
    item_id: int,
    price_per_day: float = Form(...),
    total_qty: int = Form(...),
    broken_qty: int = Form(...),
    db: Session = Depends(get_db),
    user: models.User = Depends(auth.require_role(["admin"]))
):
    item = db.query(models.Equipment).filter(models.Equipment.id == item_id).first()
    if item:
        item.price_per_day = price_per_day
        item.total_qty = max(0, total_qty)
        item.broken_qty = min(item.total_qty, max(0, broken_qty))
        db.commit()
    return RedirectResponse(url="/admin", status_code=303)

@app.post("/admin/user/role/{target_user_id}")
def change_user_role(
    target_user_id: int,
    role: str = Form(...),
    db: Session = Depends(get_db),
    user: models.User = Depends(auth.require_role(["admin"]))
):
    target = db.query(models.User).filter(models.User.id == target_user_id).first()
    if target and role in ["client", "manager", "admin"]:
        target.role = role
        db.commit()
    return RedirectResponse(url="/admin", status_code=303)
