from datetime import date
from sqlalchemy.orm import Session
from sqlalchemy import and_
from . import models

def check_availability(db: Session, equipment_id: int, start_date: date, end_date: date, req_qty: int) -> bool:
    item = db.query(models.Equipment).filter(models.Equipment.id == equipment_id).first()
    if not item or req_qty <= 0:
        return False
    
    available_stock = item.total_qty - item.broken_qty
    if available_stock < req_qty:
        return False
    
    overlapping = db.query(models.Booking).filter(
        models.Booking.equipment_id == equipment_id,
        models.Booking.status.in_(["booked", "issued", "overdue"]),
        and_(
            models.Booking.start_date <= end_date,
            models.Booking.end_date >= start_date
        )
    ).all()
    
    booked_qty = sum(b.quantity for b in overlapping)
    return (available_stock - booked_qty) >= req_qty

def create_booking(db: Session, user_id: int, equipment_id: int, start_date: date, end_date: date, qty: int):
    if end_date < start_date:
        raise ValueError("Дата окончания не может быть раньше даты начала")
    if not check_availability(db, equipment_id, start_date, end_date, qty):
        raise ValueError("Недостаточно свободного оборудования на выбранные даты")
        
    item = db.query(models.Equipment).filter(models.Equipment.id == equipment_id).first()
    days = (end_date - start_date).days + 1
    total_price = days * item.price_per_day * qty
    
    booking = models.Booking(
        user_id=user_id,
        equipment_id=equipment_id,
        quantity=qty,
        start_date=start_date,
        end_date=end_date,
        total_price=total_price,
        status="booked"
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return booking

def return_equipment(db: Session, booking_id: int, actual_return_date: date, damage_fine: float = 0.0, broken_units: int = 0, note: str = ""):
    booking = db.query(models.Booking).filter(models.Booking.id == booking_id).first()
    if not booking:
        raise ValueError("Бронирование не найдено")
    if booking.status == "returned":
        raise ValueError("Оборудование уже возвращено")
        
    booking.status = "returned"
    booking.condition_note = note
    
    overdue_days = (actual_return_date - booking.end_date).days
    overdue_fine = 0.0
    if overdue_days > 0:
        overdue_fine = overdue_days * (booking.equipment.price_per_day * 1.5) * booking.quantity
        
    total_fine = overdue_fine + max(0.0, damage_fine)
    if total_fine > 0:
        fine = models.Fine(
            booking_id=booking.id,
            amount=total_fine,
            reason=f"Просрочка: {max(0, overdue_days)} дн. Состояние: {note or 'без замечаний'}"
        )
        db.add(fine)
        
    if broken_units > 0:
        item = booking.equipment
        item.broken_qty = min(item.total_qty, item.broken_qty + broken_units)
        
    db.commit()
    return booking
