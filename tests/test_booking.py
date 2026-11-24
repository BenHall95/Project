import pytest
from datetime import date, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app import models, crud

@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    
    user = models.User(username="test_client", hashed_password="123", role="client")
    item = models.Equipment(name="Велосипед", category="Спорт", price_per_day=1000.0, total_qty=2, broken_qty=0)
    session.add_all([user, item])
    session.commit()
    yield session
    session.close()

def test_create_booking_success(db):
    start = date.today()
    end = start + timedelta(days=2)
    booking = crud.create_booking(db, user_id=1, equipment_id=1, start_date=start, end_date=end, qty=1)
    assert booking.id is not None
    assert booking.total_price == 3000.0

def test_overlapping_dates_blocked(db):
    start = date.today()
    end = start + timedelta(days=4)
    crud.create_booking(db, user_id=1, equipment_id=1, start_date=start, end_date=end, qty=2)
    with pytest.raises(ValueError):
        crud.create_booking(db, user_id=1, equipment_id=1, start_date=start + timedelta(days=2), end_date=end + timedelta(days=2), qty=1)

def test_overdue_fine_calculation(db):
    start = date.today() - timedelta(days=5)
    end = date.today() - timedelta(days=2)
    booking = crud.create_booking(db, user_id=1, equipment_id=1, start_date=start, end_date=end, qty=1)
    crud.return_equipment(db, booking.id, actual_return_date=date.today())
    fine = db.query(models.Fine).filter(models.Fine.booking_id == booking.id).first()
    assert fine is not None
    assert fine.amount == 3000.0

def test_damage_and_broken_stock(db):
    start = date.today()
    booking = crud.create_booking(db, user_id=1, equipment_id=1, start_date=start, end_date=start, qty=1)
    crud.return_equipment(db, booking.id, actual_return_date=start, damage_fine=500.0, broken_units=1, note="Сломан переключатель")
    item = db.query(models.Equipment).filter(models.Equipment.id == 1).first()
    assert item.broken_qty == 1
