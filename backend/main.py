"""
Система учета ПУ - Backend
ЭТАП 1: Базовая структура
"""
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Enum as SQLEnum, Float, Date
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from sqlalchemy.sql import func
from pydantic import BaseModel
from pydantic_settings import BaseSettings
from typing import Optional, List
from datetime import datetime, timedelta, date
from jose import jwt
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import bcrypt as _bcrypt
import pandas as pd
import io
import enum
import re

# ==================== КОНФИГ ====================
class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://user:pass@localhost/pu_system"
    SECRET_KEY: str = "your-secret-key-change-me"
    ADMIN_CODE: str = "2233"
    class Config:
        env_file = ".env"

settings = Settings()

# ==================== БАЗА ДАННЫХ ====================
engine = create_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ==================== ENUM'ы ====================
class UnitType(str, enum.Enum):
    SUE = "SUE"          # Служба учета электроэнергии
    LAB = "LAB"          # Лаборатория
    ESK = "ESK"          # ЭСК (центральный админ)
    RES = "RES"          # РЭС (7 штук)
    ESK_UNIT = "ESK_UNIT"  # Подразделение ЭСК (7 штук)

class RoleCode(str, enum.Enum):
    SUE_ADMIN = "SUE_ADMIN"      # СУЭ - видит всё, перемещает РЭС, удаляет, управляет
    LAB_USER = "LAB_USER"        # Лаборатория - загружает реестры
    ESK_ADMIN = "ESK_ADMIN"      # ЭСК Админ - видит все ЭСК, перемещает между ЭСК
    RES_USER = "RES_USER"        # Пользователь РЭС - только свой РЭС
    ESK_USER = "ESK_USER"        # Пользователь ЭСК - только своё подразделение ЭСК

class PUStatus(str, enum.Enum):
    SKLAD = "SKLAD"          # На складе (по умолчанию)
    TECHPRIS = "TECHPRIS"    # Техприс
    ZAMENA = "ZAMENA"        # Замена
    IZHC = "IZHC"            # ИЖЦ
    INSTALLED = "INSTALLED"  # Установлен

class ApprovalStatus(str, enum.Enum):
    NONE = "NONE"            # Не отправлено
    PENDING = "PENDING"      # На согласовании
    APPROVED = "APPROVED"    # Согласовано
    REJECTED = "REJECTED"    # Отклонено

# ==================== МОДЕЛИ БД ====================

class Unit(Base):
    """Подразделения"""
    __tablename__ = "units"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    code = Column(String(50), unique=True)
    short_code = Column(String(10))  # с, а, д, л, т, х, к для ТЗ
    unit_type = Column(SQLEnum(UnitType))
    parent_id = Column(Integer, ForeignKey("units.id"))
    is_active = Column(Boolean, default=True)

class Role(Base):
    """Роли"""
    __tablename__ = "roles"
    id = Column(Integer, primary_key=True)
    name = Column(String(100))
    code = Column(SQLEnum(RoleCode), unique=True)

class User(Base):
    """Пользователи"""
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True)
    password_hash = Column(String(255))
    full_name = Column(String(200))
    role_id = Column(Integer, ForeignKey("roles.id"))
    unit_id = Column(Integer, ForeignKey("units.id"))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    role = relationship("Role")
    unit = relationship("Unit")

class PURegister(Base):
    """Реестр загрузок ПУ"""
    __tablename__ = "pu_registers"
    id = Column(Integer, primary_key=True)
    filename = Column(String(255))
    uploaded_by = Column(Integer, ForeignKey("users.id"))
    uploaded_at = Column(DateTime, server_default=func.now())
    items_count = Column(Integer, default=0)
    uploader = relationship("User")

class PUItem(Base):
    """Прибор учета - расширенная карточка"""
    __tablename__ = "pu_items"
    id = Column(Integer, primary_key=True)
    register_id = Column(Integer, ForeignKey("pu_registers.id"))
    
    # Базовые поля (из импорта лаборатории)
    serial_number = Column(String(100), index=True)  # Заводской номер
    pu_type = Column(String(500))  # Тип счетчика
    
    # Местоположение
    target_unit_id = Column(Integer, ForeignKey("units.id"))  # Куда назначен
    current_unit_id = Column(Integer, ForeignKey("units.id"))  # Где сейчас
    
    # Статус и тип работы
    status = Column(SQLEnum(PUStatus), default=PUStatus.SKLAD)
    
    # Поля карточки РЭС
    tz_number = Column(String(50))  # Номер ТЗ
    faza = Column(String(20))  # Фазность (из справочника)
    voltage = Column(String(20))  # Уровень напряжения 0.23, 0.4, 6, 10
    power = Column(Float)  # Мощность кВт
    
    # Для Техприс и ЭСК
    contract_number = Column(String(50))  # Договор ТП формат ххххх-хх-хххххххх-х
    contract_date = Column(Date)  # Дата заключения
    plan_date = Column(Date)  # Планируемая дата исполнения
    consumer = Column(String(500))  # Потребитель
    address = Column(Text)  # Адрес
    
    # Для Замена и ИЖЦ
    ls_number = Column(String(50))  # Лицевой счет
    
    # СМР
    smr_executor = Column(String(20))  # РСК или ЭСК
    smr_date = Column(Date)  # Дата выполнения СМР
    smr_master_id = Column(Integer, ForeignKey("esk_masters.id"))  # Мастер ЭСК
    
    # ТТР для РЭС
    ttr_ou_id = Column(Integer, ForeignKey("ttr_res.id"))  # ТТР организации учета
    ttr_ol_id = Column(Integer, ForeignKey("ttr_res.id"))  # ТТР обустройство линии
    ttr_or_id = Column(Integer, ForeignKey("ttr_res.id"))  # ТТР распред. щита
    
    # ТТР для ЭСК
    ttr_esk_id = Column(Integer, ForeignKey("ttr_esk.id"))  # ТТР ЭСК
    trubostoyka = Column(Boolean, default=False)  # Трубостойка да/нет
    
    # Материалы (JSON или отдельная таблица)
    materials_used = Column(Boolean, default=False)  # Материалы использованы
    
    # Согласование (для ЭСК)
    approval_status = Column(SQLEnum(ApprovalStatus), default=ApprovalStatus.NONE)
    approved_by = Column(Integer, ForeignKey("users.id"))
    approved_at = Column(DateTime)
    
    # Заявка ЭСК
    request_number = Column(String(50))  # Номер заявки
    
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # Relationships
    register = relationship("PURegister")
    target_unit = relationship("Unit", foreign_keys=[target_unit_id])
    current_unit = relationship("Unit", foreign_keys=[current_unit_id])
    ttr_ou = relationship("TTR_RES", foreign_keys=[ttr_ou_id])
    ttr_ol = relationship("TTR_RES", foreign_keys=[ttr_ol_id])
    ttr_or = relationship("TTR_RES", foreign_keys=[ttr_or_id])
    ttr_esk = relationship("TTR_ESK", foreign_keys=[ttr_esk_id])

class PUMovement(Base):
    """История перемещений"""
    __tablename__ = "pu_movements"
    id = Column(Integer, primary_key=True)
    pu_item_id = Column(Integer, ForeignKey("pu_items.id"))
    from_unit_id = Column(Integer, ForeignKey("units.id"))
    to_unit_id = Column(Integer, ForeignKey("units.id"))
    moved_by = Column(Integer, ForeignKey("users.id"))
    moved_at = Column(DateTime, server_default=func.now())
    comment = Column(Text)

class TTR_RES(Base):
    """Справочник ТТР для РЭС"""
    __tablename__ = "ttr_res"
    id = Column(Integer, primary_key=True)
    code = Column(String(50))  # ТТР-1 ОУ, ТТР-2 ОЛ и т.д.
    name = Column(String(200))
    ttr_type = Column(String(20))  # OU, OL, OR (организация учета, линии, распред)
    pu_types = Column(Text)  # Для каких типов ПУ применим (JSON или через запятую)
    is_active = Column(Boolean, default=True)

class TTR_ESK(Base):
    """Справочник ТТР для ЭСК (со стоимостью)"""
    __tablename__ = "ttr_esk"
    id = Column(Integer, primary_key=True)
    code = Column(String(50))
    name = Column(String(200))
    price = Column(Float, default=0)  # Стоимость ЛСР
    price_with_truba = Column(Float, default=0)  # Стоимость с трубостойкой
    is_active = Column(Boolean, default=True)

class Material(Base):
    """Справочник материалов"""
    __tablename__ = "materials"
    id = Column(Integer, primary_key=True)
    name = Column(String(200))
    unit = Column(String(50))  # шт, м, кг
    is_active = Column(Boolean, default=True)

class TTR_Material(Base):
    """Связь ТТР и материалов (сколько чего нужно)"""
    __tablename__ = "ttr_materials"
    id = Column(Integer, primary_key=True)
    ttr_res_id = Column(Integer, ForeignKey("ttr_res.id"))
    material_id = Column(Integer, ForeignKey("materials.id"))
    quantity = Column(Float, default=0)

class PUMaterial(Base):
    """Использованные материалы в конкретном ПУ"""
    __tablename__ = "pu_materials"
    id = Column(Integer, primary_key=True)
    pu_item_id = Column(Integer, ForeignKey("pu_items.id"))
    material_id = Column(Integer, ForeignKey("materials.id"))
    quantity = Column(Float, default=0)
    used = Column(Boolean, default=True)  # Галочка использован/нет

class ESKMaster(Base):
    """Справочник мастеров ЭСК"""
    __tablename__ = "esk_masters"
    id = Column(Integer, primary_key=True)
    unit_id = Column(Integer, ForeignKey("units.id"))  # Подразделение ЭСК
    full_name = Column(String(200))
    is_active = Column(Boolean, default=True)
    unit = relationship("Unit")

class PUTypeReference(Base):
    """Справочник типов ПУ для автоопределения"""
    __tablename__ = "pu_type_reference"
    id = Column(Integer, primary_key=True)
    pattern = Column(String(200))  # Паттерн для поиска (Нартис И100 SP)
    faza = Column(String(20))  # Фазность
    voltage = Column(String(20))  # Напряжение
    for_esk = Column(Boolean, default=False)  # Для ЭСК или РЭС
    is_active = Column(Boolean, default=True)

# ==================== АВТОРИЗАЦИЯ ====================
security = HTTPBearer()

def hash_password(password: str) -> str:
    return _bcrypt.hashpw(password.encode(), _bcrypt.gensalt()).decode()

def verify_password(plain: str, hashed: str) -> bool:
    return _bcrypt.checkpw(plain.encode(), hashed.encode())

def create_token(user_id: int) -> str:
    expire = datetime.utcnow() + timedelta(hours=24)
    return jwt.encode({"sub": str(user_id), "exp": expire}, settings.SECRET_KEY)

def get_current_user(creds: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)) -> User:
    try:
        payload = jwt.decode(creds.credentials, settings.SECRET_KEY, algorithms=["HS256"])
        user = db.query(User).filter(User.id == int(payload["sub"])).first()
        if not user or not user.is_active:
            raise HTTPException(401, "Не авторизован")
        return user
    except:
        raise HTTPException(401, "Неверный токен")

# Проверки ролей
def is_sue_admin(user: User) -> bool:
    return user.role.code == RoleCode.SUE_ADMIN

def is_lab_user(user: User) -> bool:
    return user.role.code == RoleCode.LAB_USER

def is_esk_admin(user: User) -> bool:
    return user.role.code == RoleCode.ESK_ADMIN

def is_res_user(user: User) -> bool:
    return user.role.code == RoleCode.RES_USER

def is_esk_user(user: User) -> bool:
    return user.role.code == RoleCode.ESK_USER

# ==================== АВТООПРЕДЕЛЕНИЕ ТИПА ПУ ====================
def detect_pu_type_params(pu_type: str, db: Session) -> dict:
    """
    Определяет фазность и напряжение по паттерну из справочника.
    Например: "НАРТИС-И100-W113-2-A1R1-230-5-80A..." -> ищем паттерн "НАРТИС-И100-W113"
    """
    if not pu_type:
        return {}
    
    pu_type_upper = pu_type.upper().strip()
    
    # Получаем все паттерны из справочника
    patterns = db.query(PUTypeReference).filter(PUTypeReference.is_active == True).all()
    
    # Ищем подходящий паттерн (от более длинного к короткому для точности)
    patterns_sorted = sorted(patterns, key=lambda p: len(p.pattern) if p.pattern else 0, reverse=True)
    
    for p in patterns_sorted:
        if not p.pattern:
            continue
        pattern_upper = p.pattern.upper().strip()
        if pu_type_upper.startswith(pattern_upper) or pattern_upper in pu_type_upper:
            result = {}
            if p.faza:
                result['faza'] = p.faza
            if p.voltage:
                result['voltage'] = p.voltage
            return result
    
    return {}

def get_visible_units(user: User, db: Session) -> List[int]:
    """Какие подразделения видит пользователь"""
    if is_sue_admin(user):
        return [u.id for u in db.query(Unit).all()]
    if is_esk_admin(user):
        return [u.id for u in db.query(Unit).filter(Unit.unit_type.in_([UnitType.ESK, UnitType.ESK_UNIT])).all()]
    if is_lab_user(user):
        return [user.unit_id] if user.unit_id else []
    # RES_USER и ESK_USER видят только своё подразделение
    return [user.unit_id] if user.unit_id else []

def can_move_pu(user: User, pu_item, target_unit, db: Session) -> tuple[bool, str]:
    """Проверка прав на перемещение"""
    if is_sue_admin(user):
        # СУЭ может перемещать только ПУ из РЭС в РЭС
        if pu_item.current_unit and pu_item.current_unit.unit_type in [UnitType.ESK, UnitType.ESK_UNIT]:
            return False, "СУЭ не может перемещать ПУ из ЭСК"
        if target_unit.unit_type in [UnitType.ESK, UnitType.ESK_UNIT]:
            return False, "СУЭ может перемещать только в РЭС"
        return True, ""
    
    if is_esk_admin(user):
        # ЭСК админ может перемещать только между ЭСК
        if pu_item.current_unit and pu_item.current_unit.unit_type not in [UnitType.ESK, UnitType.ESK_UNIT]:
            return False, "ЭСК может перемещать только ПУ из ЭСК"
        if target_unit.unit_type not in [UnitType.ESK, UnitType.ESK_UNIT]:
            return False, "ЭСК может перемещать только в ЭСК"
        return True, ""
    
    return False, "Нет прав на перемещение"

# ==================== PYDANTIC СХЕМЫ ====================
class LoginReq(BaseModel):
    username: str
    password: str

class TokenResp(BaseModel):
    access_token: str

class UserResp(BaseModel):
    id: int
    username: str
    full_name: str
    role_code: str
    role_name: str
    unit_id: Optional[int]
    unit_name: Optional[str]
    unit_type: Optional[str]
    visible_units: List[int] = []

class UnitResp(BaseModel):
    id: int
    name: str
    code: str
    unit_type: str
    short_code: Optional[str]

class MoveReq(BaseModel):
    pu_item_ids: List[int]
    to_unit_id: int
    comment: Optional[str] = None

class DeleteReq(BaseModel):
    pu_item_ids: List[int]
    admin_code: str

class PUCardUpdate(BaseModel):
    status: Optional[str] = None
    faza: Optional[str] = None
    voltage: Optional[str] = None
    power: Optional[float] = None
    contract_number: Optional[str] = None
    contract_date: Optional[date] = None
    plan_date: Optional[date] = None
    consumer: Optional[str] = None
    address: Optional[str] = None
    ls_number: Optional[str] = None
    smr_executor: Optional[str] = None
    smr_date: Optional[date] = None
    ttr_ou_id: Optional[int] = None
    ttr_ol_id: Optional[int] = None
    ttr_or_id: Optional[int] = None
    ttr_esk_id: Optional[int] = None
    trubostoyka: Optional[bool] = None

# ==================== ПРИЛОЖЕНИЕ ====================
app = FastAPI(title="Система учета ПУ")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

Base.metadata.create_all(bind=engine)

# ==================== API: AUTH ====================
@app.get("/")
def root():
    return {"status": "ok", "message": "Система учета ПУ v2"}

@app.post("/api/auth/login", response_model=TokenResp)
def login(req: LoginReq, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == req.username).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(401, "Неверный логин или пароль")
    return {"access_token": create_token(user.id)}

@app.get("/api/auth/me", response_model=UserResp)
def get_me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return UserResp(
        id=user.id, username=user.username, full_name=user.full_name,
        role_code=user.role.code.value, role_name=user.role.name,
        unit_id=user.unit_id, 
        unit_name=user.unit.name if user.unit else None,
        unit_type=user.unit.unit_type.value if user.unit else None,
        visible_units=get_visible_units(user, db)
    )

# ==================== API: СПРАВОЧНИКИ ====================
@app.get("/api/units", response_model=List[UnitResp])
def get_units(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    units = db.query(Unit).filter(Unit.is_active == True).all()
    return [UnitResp(id=u.id, name=u.name, code=u.code, unit_type=u.unit_type.value, short_code=u.short_code) for u in units]

@app.get("/api/roles")
def get_roles(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return [{"id": r.id, "name": r.name, "code": r.code.value} for r in db.query(Role).all()]

@app.get("/api/ttr/res")
def get_ttr_res(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Справочник ТТР для РЭС"""
    items = db.query(TTR_RES).filter(TTR_RES.is_active == True).all()
    return [{"id": t.id, "code": t.code, "name": t.name, "ttr_type": t.ttr_type} for t in items]

@app.get("/api/ttr/esk")
def get_ttr_esk(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Справочник ТТР для ЭСК"""
    items = db.query(TTR_ESK).filter(TTR_ESK.is_active == True).all()
    return [{"id": t.id, "code": t.code, "name": t.name, "price": t.price, "price_with_truba": t.price_with_truba} for t in items]

@app.get("/api/masters")
def get_masters(unit_id: Optional[int] = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Справочник мастеров ЭСК"""
    q = db.query(ESKMaster).filter(ESKMaster.is_active == True)
    if unit_id:
        q = q.filter(ESKMaster.unit_id == unit_id)
    return [{"id": m.id, "full_name": m.full_name, "unit_id": m.unit_id, "unit_name": m.unit.name if m.unit else None} for m in q.all()]

# ==================== API: ПОЛЬЗОВАТЕЛИ (только СУЭ) ====================
@app.get("/api/users")
def get_users(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not is_sue_admin(user):
        raise HTTPException(403, "Нет доступа")
    users = db.query(User).all()
    return [{
        "id": u.id, "username": u.username, "full_name": u.full_name, "is_active": u.is_active,
        "role": {"id": u.role.id, "name": u.role.name, "code": u.role.code.value} if u.role else None,
        "unit": {"id": u.unit.id, "name": u.unit.name, "unit_type": u.unit.unit_type.value} if u.unit else None
    } for u in users]

@app.post("/api/users")
def create_user(data: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not is_sue_admin(user):
        raise HTTPException(403, "Нет доступа")
    if db.query(User).filter(User.username == data["username"]).first():
        raise HTTPException(400, "Логин уже занят")
    new_user = User(
        username=data["username"], password_hash=hash_password(data["password"]),
        full_name=data["full_name"], role_id=data["role_id"], unit_id=data.get("unit_id")
    )
    db.add(new_user)
    db.commit()
    return {"id": new_user.id}

@app.put("/api/users/{user_id}")
def update_user(user_id: int, data: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not is_sue_admin(user):
        raise HTTPException(403, "Нет доступа")
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(404, "Не найден")
    for k, v in data.items():
        if k != "password" and hasattr(u, k):
            setattr(u, k, v)
    db.commit()
    return {"ok": True}

# ==================== API: ПУ ====================
@app.get("/api/pu/dashboard")
def dashboard(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    visible = get_visible_units(user, db)
    
    q = db.query(PUItem)
    if is_lab_user(user):
        regs = db.query(PURegister.id).filter(PURegister.uploaded_by == user.id)
        q = q.filter(PUItem.register_id.in_(regs))
    elif not is_sue_admin(user):
        q = q.filter(PUItem.current_unit_id.in_(visible))
    
    total = q.count()
    sklad = q.filter(PUItem.status == PUStatus.SKLAD).count()
    techpris = q.filter(PUItem.status == PUStatus.TECHPRIS).count()
    zamena = q.filter(PUItem.status == PUStatus.ZAMENA).count()
    izhc = q.filter(PUItem.status == PUStatus.IZHC).count()
    installed = q.filter(PUItem.status == PUStatus.INSTALLED).count()
    
    # Последние загрузки
    reg_q = db.query(PURegister)
    if is_lab_user(user):
        reg_q = reg_q.filter(PURegister.uploaded_by == user.id)
    recent = reg_q.order_by(PURegister.uploaded_at.desc()).limit(5).all()
    
    # Количество на согласовании (для РЭС)
    pending_approval = 0
    if is_res_user(user) and user.unit_id:
        # Ищем ПУ в ЭСК которые привязаны к РЭС пользователя и ждут согласования
        res_code = user.unit.code if user.unit else ""
        esk_code = res_code.replace("RES_", "ESK_") if res_code else ""
        esk_unit = db.query(Unit).filter(Unit.code == esk_code).first()
        if esk_unit:
            pending_approval = db.query(PUItem).filter(
                PUItem.current_unit_id == esk_unit.id,
                PUItem.approval_status == ApprovalStatus.PENDING
            ).count()
    
    return {
        "total_pu": total, "sklad": sklad, "techpris": techpris, 
        "zamena": zamena, "izhc": izhc, "installed": installed,
        "pending_approval": pending_approval,
        "recent_registers": [{"id": r.id, "filename": r.filename, "items_count": r.items_count, "uploaded_at": r.uploaded_at} for r in recent]
    }

@app.get("/api/pu/items")
def get_items(
    page: int = 1, size: int = 50,
    search: Optional[str] = None, 
    status: Optional[str] = None, 
    unit_id: Optional[int] = None,
    exclude_esk: Optional[bool] = None,
    contract: Optional[str] = None,
    ls: Optional[str] = None,
    filter: Optional[str] = None,  # all, work, done
    db: Session = Depends(get_db), 
    user: User = Depends(get_current_user)
):
    visible = get_visible_units(user, db)
    q = db.query(PUItem)
    
    if is_lab_user(user):
        regs = db.query(PURegister.id).filter(PURegister.uploaded_by == user.id)
        q = q.filter(PUItem.register_id.in_(regs))
    elif not is_sue_admin(user):
        q = q.filter(PUItem.current_unit_id.in_(visible))
    
    if search:
        q = q.filter(PUItem.serial_number.ilike(f"%{search}%"))
    if status:
        q = q.filter(PUItem.status == status)
    if unit_id:
        q = q.filter(PUItem.current_unit_id == unit_id)
    if exclude_esk:
        esk_units = db.query(Unit.id).filter(Unit.unit_type.in_([UnitType.ESK, UnitType.ESK_UNIT]))
        q = q.filter(~PUItem.current_unit_id.in_(esk_units))
    if contract:
        q = q.filter(PUItem.contract_number.ilike(f"%{contract}%"))
    if ls:
    q = q.filter(PUItem.ls_number.ilike(f"%{ls}%"))

# Фильтр по типу реестра
if filter == 'work':
    # В работе: не на складе И (нет ТЗ И нет Заявки)
    q = q.filter(
        PUItem.status != PUStatus.SKLAD,
        (PUItem.tz_number == None) | (PUItem.tz_number == ""),
        (PUItem.request_number == None) | (PUItem.request_number == "")
    )
elif filter == 'done':
    # Завершённые: есть ТЗ ИЛИ есть Заявка
    q = q.filter(
        (PUItem.tz_number != None) & (PUItem.tz_number != "") |
        (PUItem.request_number != None) & (PUItem.request_number != "")
    )

total = q.count()
    items = q.order_by(PUItem.created_at.desc()).offset((page-1)*size).limit(size).all()
    
    return {
        "items": [{
            "id": i.id, "serial_number": i.serial_number, "pu_type": i.pu_type,
            "status": i.status.value, "current_unit_id": i.current_unit_id,
            "current_unit_name": i.current_unit.name if i.current_unit else None,
            "current_unit_type": i.current_unit.unit_type.value if i.current_unit else None,
            "tz_number": i.tz_number, "request_number": i.request_number,
            "contract_number": i.contract_number,
            "ls_number": i.ls_number, "consumer": i.consumer,
            "smr_date": i.smr_date.isoformat() if i.smr_date else None,
            "approval_status": i.approval_status.value if i.approval_status else None,
            "uploaded_at": i.register.uploaded_at if i.register else None
        } for i in items],
        "total": total, "page": page, "size": size, "pages": (total + size - 1) // size
    }

@app.get("/api/pu/detect-type")
def detect_type(pu_type: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Определить фазность и напряжение по типу ПУ"""
    result = detect_pu_type_params(pu_type, db)
    return result

@app.get("/api/pu/items/{item_id}")
def get_item_detail(item_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Полная карточка ПУ"""
    item = db.query(PUItem).filter(PUItem.id == item_id).first()
    if not item:
        raise HTTPException(404, "ПУ не найден")
    
    return {
        "id": item.id,
        "serial_number": item.serial_number,
        "pu_type": item.pu_type,
        "status": item.status.value,
        "current_unit_id": item.current_unit_id,
        "current_unit_name": item.current_unit.name if item.current_unit else None,
        "current_unit_type": item.current_unit.unit_type.value if item.current_unit else None,
        "tz_number": item.tz_number,
        "faza": item.faza,
        "voltage": item.voltage,
        "power": item.power,
        "contract_number": item.contract_number,
        "contract_date": item.contract_date.isoformat() if item.contract_date else None,
        "plan_date": item.plan_date.isoformat() if item.plan_date else None,
        "consumer": item.consumer,
        "address": item.address,
        "ls_number": item.ls_number,
        "smr_executor": item.smr_executor,
        "smr_date": item.smr_date.isoformat() if item.smr_date else None,
        "ttr_ou_id": item.ttr_ou_id,
        "ttr_ol_id": item.ttr_ol_id,
        "ttr_or_id": item.ttr_or_id,
        "ttr_esk_id": item.ttr_esk_id,
        "trubostoyka": item.trubostoyka,
        "materials_used": item.materials_used,
        "approval_status": item.approval_status.value if item.approval_status else None,
        "request_number": item.request_number,
    }

@app.put("/api/pu/items/{item_id}")
def update_item(item_id: int, data: PUCardUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Обновление карточки ПУ"""
    item = db.query(PUItem).filter(PUItem.id == item_id).first()
    if not item:
        raise HTTPException(404, "ПУ не найден")
    
    # Проверка доступа - СУЭ и ЭСК Админ только просмотр
    if is_sue_admin(user):
        raise HTTPException(403, "СУЭ может только просматривать карточки ПУ")
    if is_esk_admin(user):
        raise HTTPException(403, "ЭСК Админ может только просматривать и перемещать ПУ")
    
    visible = get_visible_units(user, db)
    if item.current_unit_id not in visible:
        raise HTTPException(403, "Нет доступа к этому ПУ")
    
    # Валидация договора
    if data.contract_number:
        pattern = r'^\d{5}-\d{2}-\d{8}-\d$'
        if not re.match(pattern, data.contract_number):
            raise HTTPException(400, "Неверный формат договора. Ожидается: ххххх-хх-хххххххх-х")
        # Проверка дубликата
        existing = db.query(PUItem).filter(
            PUItem.contract_number == data.contract_number,
            PUItem.id != item_id
        ).first()
        if existing:
            raise HTTPException(400, f"Договор уже существует в системе (ПУ {existing.serial_number})")
    
    # Автозаполнение фазности и напряжения при смене статуса со Склада
    if data.status and data.status != 'SKLAD' and item.status == PUStatus.SKLAD:
        detected = detect_pu_type_params(item.pu_type, db)
        if detected:
            if not data.faza and not item.faza and detected.get('faza'):
                data.faza = detected['faza']
            if not data.voltage and not item.voltage and detected.get('voltage'):
                data.voltage = detected['voltage']
    
    # Обновляем поля
    for key, value in data.dict(exclude_unset=True).items():
        if value is not None:
            setattr(item, key, value)
    
    db.commit()
    return {"ok": True}

@app.get("/api/pu/registers")
def get_registers(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(PURegister)
    if is_lab_user(user):
        q = q.filter(PURegister.uploaded_by == user.id)
    elif not is_sue_admin(user):
        return []
    regs = q.order_by(PURegister.uploaded_at.desc()).all()
    return [{"id": r.id, "filename": r.filename, "items_count": r.items_count, "uploaded_at": r.uploaded_at} for r in regs]

@app.post("/api/pu/upload")
async def upload_register(file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Загрузка реестра ПУ - только Лаборатория"""
    if not is_lab_user(user):
        raise HTTPException(403, "Только Лаборатория может загружать реестры")
    
    contents = await file.read()
    xl = pd.ExcelFile(io.BytesIO(contents))
    
    # Ищем лист с данными
    df = None
    for sheet in xl.sheet_names:
        temp_df = pd.read_excel(xl, sheet_name=sheet)
        for col in temp_df.columns:
            if 'заводской' in str(col).lower() or ('номер' in str(col).lower() and 'пу' in str(col).lower()):
                df = temp_df
                break
        if df is not None:
            break
    if df is None:
        df = pd.read_excel(io.BytesIO(contents))
    
    register = PURegister(filename=file.filename, uploaded_by=user.id, items_count=0)
    db.add(register)
    db.commit()
    
    # Поиск колонок
    serial_col = type_col = unit_col = None
    for col in df.columns:
        col_lower = str(col).lower()
        if 'заводской' in col_lower or ('номер' in col_lower and 'пу' in col_lower):
            serial_col = col
        elif 'тип' in col_lower:
            type_col = col
        elif 'подразделение' in col_lower:
            unit_col = col
    
    if not serial_col:
        raise HTTPException(400, "Не найдена колонка 'Заводской номер ПУ'")
    
    # Словарь подразделений
    units_map = {}
    for u in db.query(Unit).all():
        units_map[u.name.lower()] = u
        if u.code:
            units_map[u.code.lower()] = u
    
    count = 0
    for _, row in df.iterrows():
        serial = str(row.get(serial_col, '')).strip()
        if not serial or serial == 'nan':
            continue
        
        pu_type = str(row.get(type_col, '')).strip() if type_col else None
        if pu_type == 'nan':
            pu_type = None
        
        target_unit = None
        if unit_col:
            unit_name = str(row.get(unit_col, '')).strip().lower()
            if unit_name and unit_name != 'nan':
                target_unit = units_map.get(unit_name)
                if not target_unit:
                    for key, u in units_map.items():
                        if unit_name in key or key in unit_name:
                            target_unit = u
                            break
        
        # По умолчанию статус СКЛАД
        item = PUItem(
            register_id=register.id,
            pu_type=pu_type[:500] if pu_type else None,
            serial_number=serial,
            target_unit_id=target_unit.id if target_unit else None,
            current_unit_id=target_unit.id if target_unit else None,
            status=PUStatus.SKLAD
        )
        db.add(item)
        count += 1
    
    register.items_count = count
    db.commit()
    return {"id": register.id, "filename": register.filename, "items_count": count, "uploaded_at": register.uploaded_at}

@app.post("/api/pu/move")
def move_items(req: MoveReq, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Перемещение ПУ"""
    target = db.query(Unit).filter(Unit.id == req.to_unit_id).first()
    if not target:
        raise HTTPException(404, "Подразделение не найдено")
    
    items = db.query(PUItem).filter(PUItem.id.in_(req.pu_item_ids)).all()
    if not items:
        raise HTTPException(404, "ПУ не найдены")
    
    moved = 0
    for item in items:
        can_move, error = can_move_pu(user, item, target, db)
        if not can_move:
            raise HTTPException(403, error)
        
        mov = PUMovement(pu_item_id=item.id, from_unit_id=item.current_unit_id, to_unit_id=target.id, moved_by=user.id, comment=req.comment)
        db.add(mov)
        item.current_unit_id = target.id
        moved += 1
    
    db.commit()
    return {"moved": moved}

@app.post("/api/pu/delete")
def delete_items(req: DeleteReq, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Удаление ПУ - только СУЭ с кодом"""
    if not is_sue_admin(user):
        raise HTTPException(403, "Только СУЭ может удалять ПУ")
    if req.admin_code != settings.ADMIN_CODE:
        raise HTTPException(403, "Неверный код администратора")
    
    # Удаляем связанные данные
    db.query(PUMovement).filter(PUMovement.pu_item_id.in_(req.pu_item_ids)).delete(synchronize_session=False)
    db.query(PUMaterial).filter(PUMaterial.pu_item_id.in_(req.pu_item_ids)).delete(synchronize_session=False)
    deleted = db.query(PUItem).filter(PUItem.id.in_(req.pu_item_ids)).delete(synchronize_session=False)
    
    db.commit()
    return {"deleted": deleted}

@app.post("/api/pu/clear-database")
def clear_database(data: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Очистка базы данных - только СУЭ с кодом"""
    if not is_sue_admin(user):
        raise HTTPException(403, "Только СУЭ может очищать базу")
    if data.get("admin_code") != settings.ADMIN_CODE:
        raise HTTPException(403, "Неверный код администратора")
    
    db.query(PUMaterial).delete()
    db.query(PUMovement).delete()
    db.query(PUItem).delete()
    db.query(PURegister).delete()
    db.commit()
    
    return {"message": "База очищена"}

# ==================== API: СОГЛАСОВАНИЕ (ЭСК -> РЭС) ====================
@app.post("/api/pu/items/{item_id}/send-approval")
def send_for_approval(item_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Отправить на согласование (ЭСК)"""
    if not is_esk_user(user) and not is_esk_admin(user):
        raise HTTPException(403, "Только ЭСК может отправлять на согласование")
    
    item = db.query(PUItem).filter(PUItem.id == item_id).first()
    if not item:
        raise HTTPException(404, "ПУ не найден")
    
    item.approval_status = ApprovalStatus.PENDING
    db.commit()
    return {"ok": True}

@app.post("/api/pu/send-approval-batch")
def send_approval_batch(data: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Массовая отправка на согласование (ЭСК)"""
    if not is_esk_user(user) and not is_esk_admin(user):
        raise HTTPException(403, "Только ЭСК может отправлять на согласование")
    
    item_ids = data.get("item_ids", [])
    if not item_ids:
        raise HTTPException(400, "Не выбраны ПУ")
    
    updated = db.query(PUItem).filter(
        PUItem.id.in_(item_ids),
        PUItem.approval_status != ApprovalStatus.APPROVED  # Не трогаем уже согласованные
    ).update({"approval_status": ApprovalStatus.PENDING}, synchronize_session=False)
    
    db.commit()
    return {"updated": updated}

@app.post("/api/pu/items/{item_id}/approve")
def approve_item(item_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Согласовать (РЭС)"""
    if not is_res_user(user) and not is_sue_admin(user):
        raise HTTPException(403, "Только РЭС может согласовывать")
    
    item = db.query(PUItem).filter(PUItem.id == item_id).first()
    if not item:
        raise HTTPException(404, "ПУ не найден")
    
    item.approval_status = ApprovalStatus.APPROVED
    item.approved_by = user.id
    item.approved_at = datetime.utcnow()
    db.commit()
    return {"ok": True}

@app.get("/api/pu/pending-approval")
def get_pending_approval(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Список ПУ на согласовании для РЭС"""
    if not is_res_user(user) and not is_sue_admin(user):
        raise HTTPException(403, "Нет доступа")
    
    # Находим соответствующий ЭСК для этого РЭС
    if is_res_user(user) and user.unit:
        esk_code = user.unit.code.replace("RES_", "ESK_") if user.unit.code else ""
        esk_unit = db.query(Unit).filter(Unit.code == esk_code).first()
        if esk_unit:
            items = db.query(PUItem).filter(
                PUItem.current_unit_id == esk_unit.id,
                PUItem.approval_status == ApprovalStatus.PENDING
            ).all()
        else:
            items = []
    else:
        # СУЭ видит все на согласовании
        items = db.query(PUItem).filter(PUItem.approval_status == ApprovalStatus.PENDING).all()
    
    return [{
        "id": i.id, "serial_number": i.serial_number, "pu_type": i.pu_type,
        "current_unit_name": i.current_unit.name if i.current_unit else None,
        "contract_number": i.contract_number, "consumer": i.consumer
    } for i in items]

# ==================== API: СПРАВОЧНИКИ (CRUD) ====================

# --- Мастера ЭСК ---
@app.post("/api/masters")
def create_master(data: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not is_esk_admin(user) and not is_sue_admin(user):
        raise HTTPException(403, "Нет доступа")
    master = ESKMaster(full_name=data["full_name"], unit_id=data["unit_id"])
    db.add(master)
    db.commit()
    return {"id": master.id}

@app.put("/api/masters/{master_id}")
def update_master(master_id: int, data: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not is_esk_admin(user) and not is_sue_admin(user):
        raise HTTPException(403, "Нет доступа")
    m = db.query(ESKMaster).filter(ESKMaster.id == master_id).first()
    if not m:
        raise HTTPException(404, "Не найден")
    for k, v in data.items():
        if hasattr(m, k):
            setattr(m, k, v)
    db.commit()
    return {"ok": True}

@app.delete("/api/masters/{master_id}")
def delete_master(master_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not is_esk_admin(user) and not is_sue_admin(user):
        raise HTTPException(403, "Нет доступа")
    db.query(ESKMaster).filter(ESKMaster.id == master_id).delete()
    db.commit()
    return {"ok": True}

# --- ТТР РЭС ---
@app.post("/api/ttr/res")
def create_ttr_res(data: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not is_sue_admin(user):
        raise HTTPException(403, "Нет доступа")
    ttr = TTR_RES(code=data["code"], name=data["name"], ttr_type=data["ttr_type"], pu_types=data.get("pu_types", ""))
    db.add(ttr)
    db.commit()
    return {"id": ttr.id}

@app.put("/api/ttr/res/{ttr_id}")
def update_ttr_res(ttr_id: int, data: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not is_sue_admin(user):
        raise HTTPException(403, "Нет доступа")
    t = db.query(TTR_RES).filter(TTR_RES.id == ttr_id).first()
    if not t:
        raise HTTPException(404, "Не найден")
    for k, v in data.items():
        if hasattr(t, k):
            setattr(t, k, v)
    db.commit()
    return {"ok": True}

@app.delete("/api/ttr/res/{ttr_id}")
def delete_ttr_res(ttr_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not is_sue_admin(user):
        raise HTTPException(403, "Нет доступа")
    db.query(TTR_RES).filter(TTR_RES.id == ttr_id).update({"is_active": False})
    db.commit()
    return {"ok": True}

# --- ТТР ЭСК ---
@app.post("/api/ttr/esk")
def create_ttr_esk(data: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not is_sue_admin(user):
        raise HTTPException(403, "Нет доступа")
    ttr = TTR_ESK(code=data["code"], name=data["name"], price=data.get("price", 0), price_with_truba=data.get("price_with_truba", 0))
    db.add(ttr)
    db.commit()
    return {"id": ttr.id}

@app.put("/api/ttr/esk/{ttr_id}")
def update_ttr_esk(ttr_id: int, data: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not is_sue_admin(user):
        raise HTTPException(403, "Нет доступа")
    t = db.query(TTR_ESK).filter(TTR_ESK.id == ttr_id).first()
    if not t:
        raise HTTPException(404, "Не найден")
    for k, v in data.items():
        if hasattr(t, k):
            setattr(t, k, v)
    db.commit()
    return {"ok": True}

# --- Материалы ---
@app.get("/api/materials")
def get_materials(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    items = db.query(Material).filter(Material.is_active == True).all()
    return [{"id": m.id, "name": m.name, "unit": m.unit} for m in items]

@app.post("/api/materials")
def create_material(data: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not is_sue_admin(user):
        raise HTTPException(403, "Нет доступа")
    m = Material(name=data["name"], unit=data.get("unit", "шт"))
    db.add(m)
    db.commit()
    return {"id": m.id}

@app.put("/api/materials/{mat_id}")
def update_material(mat_id: int, data: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not is_sue_admin(user):
        raise HTTPException(403, "Нет доступа")
    m = db.query(Material).filter(Material.id == mat_id).first()
    if not m:
        raise HTTPException(404, "Не найден")
    for k, v in data.items():
        if hasattr(m, k):
            setattr(m, k, v)
    db.commit()
    return {"ok": True}

# --- Материалы к ТТР ---
@app.get("/api/ttr/res/{ttr_id}/materials")
def get_ttr_materials(ttr_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    items = db.query(TTR_Material).filter(TTR_Material.ttr_res_id == ttr_id).all()
    result = []
    for tm in items:
        mat = db.query(Material).filter(Material.id == tm.material_id).first()
        if mat:
            result.append({"id": tm.id, "material_id": mat.id, "material_name": mat.name, "unit": mat.unit, "quantity": tm.quantity})
    return result

@app.post("/api/ttr/res/{ttr_id}/materials")
def set_ttr_materials(ttr_id: int, data: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not is_sue_admin(user):
        raise HTTPException(403, "Нет доступа")
    # data = {"materials": [{"material_id": 1, "quantity": 5}, ...]}
    db.query(TTR_Material).filter(TTR_Material.ttr_res_id == ttr_id).delete()
    for m in data.get("materials", []):
        tm = TTR_Material(ttr_res_id=ttr_id, material_id=m["material_id"], quantity=m["quantity"])
        db.add(tm)
    db.commit()
    return {"ok": True}

# --- Справочник типов ПУ ---
@app.get("/api/pu-types")
def get_pu_types(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    items = db.query(PUTypeReference).filter(PUTypeReference.is_active == True).all()
    return [{"id": p.id, "pattern": p.pattern, "faza": p.faza, "voltage": p.voltage, "for_esk": p.for_esk} for p in items]

@app.post("/api/pu-types")
def create_pu_type(data: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not is_sue_admin(user):
        raise HTTPException(403, "Нет доступа")
    p = PUTypeReference(pattern=data["pattern"], faza=data.get("faza"), voltage=data.get("voltage"), for_esk=data.get("for_esk", False))
    db.add(p)
    db.commit()
    return {"id": p.id}

@app.put("/api/pu-types/{type_id}")
def update_pu_type(type_id: int, data: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not is_sue_admin(user):
        raise HTTPException(403, "Нет доступа")
    p = db.query(PUTypeReference).filter(PUTypeReference.id == type_id).first()
    if not p:
        raise HTTPException(404, "Не найден")
    for k, v in data.items():
        if hasattr(p, k):
            setattr(p, k, v)
    db.commit()
    return {"ok": True}

@app.delete("/api/pu-types/{type_id}")
def delete_pu_type(type_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not is_sue_admin(user):
        raise HTTPException(403, "Нет доступа")
    db.query(PUTypeReference).filter(PUTypeReference.id == type_id).update({"is_active": False})
    db.commit()
    return {"ok": True}

# ==================== API: ТЗ и ЗАЯВКИ ====================

@app.get("/api/tz/list")
def get_tz_list(tz_type: Optional[str] = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Список ТЗ"""
    q = db.query(PUItem).filter(PUItem.tz_number != None, PUItem.tz_number != "")
    if tz_type:
        q = q.filter(PUItem.status == tz_type)
    
    # Группируем по номеру ТЗ
    items = q.all()
    tz_map = {}
    for item in items:
        if item.tz_number not in tz_map:
            tz_map[item.tz_number] = {
                "tz_number": item.tz_number,
                "status": item.status.value,
                "unit_name": item.current_unit.name if item.current_unit else None,
                "count": 0,
                "items": []
            }
        tz_map[item.tz_number]["count"] += 1
        tz_map[item.tz_number]["items"].append(item.id)
    
    return list(tz_map.values())

@app.get("/api/tz/{tz_number}/items")
def get_tz_items(tz_number: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Получить все ПУ по номеру ТЗ"""
    items = db.query(PUItem).filter(PUItem.tz_number == tz_number).all()
    return [{
        "id": i.id,
        "serial_number": i.serial_number,
        "pu_type": i.pu_type,
        "status": i.status.value,
        "current_unit_name": i.current_unit.name if i.current_unit else None,
        "contract_number": i.contract_number,
        "consumer": i.consumer,
        "address": i.address,
        "power": i.power,
        "faza": i.faza,
        "voltage": i.voltage
    } for i in items]

@app.get("/api/tz/pending")
def get_pending_for_tz(
    status: str, 
    unit_id: Optional[int] = None, 
    power_category: Optional[int] = None,
    db: Session = Depends(get_db), 
    user: User = Depends(get_current_user)
):
    """ПУ без ТЗ для формирования с фильтром по мощности"""
    if not is_sue_admin(user):
        raise HTTPException(403, "Только СУЭ может формировать ТЗ")
    
    q = db.query(PUItem).filter(
        PUItem.status == status,
        (PUItem.tz_number == None) | (PUItem.tz_number == "")
    )
    
    if unit_id:
        q = q.filter(PUItem.current_unit_id == unit_id)
    
    # Фильтр по категории мощности
    if power_category == 1:
        q = q.filter((PUItem.power == None) | (PUItem.power < 15))
    elif power_category == 2:
        q = q.filter(PUItem.power >= 15, PUItem.power < 150)
    elif power_category == 3:
        q = q.filter(PUItem.power >= 150)
    
    # Только РЭС
    res_units = db.query(Unit.id).filter(Unit.unit_type == UnitType.RES)
    q = q.filter(PUItem.current_unit_id.in_(res_units))
    
    items = q.all()
    return [{
        "id": i.id, "serial_number": i.serial_number, "pu_type": i.pu_type,
        "current_unit_name": i.current_unit.name if i.current_unit else None,
        "current_unit_id": i.current_unit_id,
        "power": i.power
    } for i in items]

@app.post("/api/tz/create")
def create_tz(data: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Создать ТЗ с автоматическим номером"""
    if not is_sue_admin(user):
        raise HTTPException(403, "Только СУЭ может формировать ТЗ")
    
    item_ids = data["item_ids"]
    unit_id = data["unit_id"]  # РЭС
    power_category = data["power_category"]  # 1, 2 или 3
    
    # Получаем букву РЭС
    unit = db.query(Unit).filter(Unit.id == unit_id).first()
    if not unit or not unit.short_code:
        raise HTTPException(400, "РЭС не найден или не указан код")
    
    # Формируем номер: 1а/01-25
    now = datetime.utcnow()
    month = now.strftime("%m")
    year = now.strftime("%y")
    tz_number = f"{power_category}{unit.short_code}/{month}-{year}"
    
    # Проверяем уникальность
    existing = db.query(PUItem).filter(PUItem.tz_number == tz_number).first()
    if existing:
        raise HTTPException(400, f"ТЗ с номером {tz_number} уже существует")
    
    updated = db.query(PUItem).filter(PUItem.id.in_(item_ids)).update({"tz_number": tz_number}, synchronize_session=False)
    db.commit()
    
    return {"created": updated, "tz_number": tz_number}

@app.get("/api/requests/list")
def get_requests_list(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Список заявок ЭСК"""
    q = db.query(PUItem).filter(PUItem.request_number != None, PUItem.request_number != "")
    
    items = q.all()
    req_map = {}
    for item in items:
        if item.request_number not in req_map:
            req_map[item.request_number] = {
                "request_number": item.request_number,
                "unit_name": item.current_unit.name if item.current_unit else None,
                "count": 0
            }
        req_map[item.request_number]["count"] += 1
    
    return list(req_map.values())

@app.get("/api/requests/{request_number}/items")
def get_request_items(request_number: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Получить все ПУ по номеру заявки"""
    items = db.query(PUItem).filter(PUItem.request_number == request_number).all()
    return [{
        "id": i.id,
        "serial_number": i.serial_number,
        "pu_type": i.pu_type,
        "status": i.status.value,
        "current_unit_name": i.current_unit.name if i.current_unit else None,
        "contract_number": i.contract_number,
        "consumer": i.consumer,
        "address": i.address,
        "power": i.power,
        "faza": i.faza,
        "voltage": i.voltage,
        "ttr_esk_id": i.ttr_esk_id,
        "trubostoyka": i.trubostoyka
    } for i in items]

@app.get("/api/requests/pending")
def get_pending_for_request(unit_id: Optional[int] = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Согласованные ПУ для заявки ЭСК"""
    if not is_sue_admin(user):
        raise HTTPException(403, "Только СУЭ может формировать заявки")
    
    q = db.query(PUItem).filter(
        PUItem.approval_status == ApprovalStatus.APPROVED,
        (PUItem.request_number == None) | (PUItem.request_number == "")
    )
    
    # Только ЭСК
    esk_units = db.query(Unit.id).filter(Unit.unit_type == UnitType.ESK_UNIT)
    q = q.filter(PUItem.current_unit_id.in_(esk_units))
    
    if unit_id:
        q = q.filter(PUItem.current_unit_id == unit_id)
    
    items = q.all()
    return [{
        "id": i.id, "serial_number": i.serial_number, "pu_type": i.pu_type,
        "current_unit_name": i.current_unit.name if i.current_unit else None,
        "contract_number": i.contract_number, "consumer": i.consumer
    } for i in items]

@app.post("/api/requests/create")
def create_request(data: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Создать заявку ЭСК с автоматическим номером"""
    if not is_sue_admin(user):
        raise HTTPException(403, "Только СУЭ может формировать заявки")
    
    item_ids = data["item_ids"]
    
    # Автоматический номер: следующий по порядку в текущем году
    current_year = datetime.utcnow().year
    year_short = str(current_year)[-2:]  # "25"
    
    # Ищем последний номер заявки за этот год
    last_request = db.query(PUItem).filter(
        PUItem.request_number != None,
        PUItem.request_number != "",
        PUItem.request_number.like(f"%-{year_short}")
    ).order_by(PUItem.request_number.desc()).first()
    
    if last_request and last_request.request_number:
        # Извлекаем номер: "5-25" -> 5
        try:
            last_num = int(last_request.request_number.split("-")[0])
            next_num = last_num + 1
        except:
            next_num = 1
    else:
        next_num = 1
    
    request_number = f"{next_num}-{year_short}"
    
    updated = db.query(PUItem).filter(PUItem.id.in_(item_ids)).update({"request_number": request_number}, synchronize_session=False)
    db.commit()
    
    return {"created": updated, "request_number": request_number}


@app.get("/api/memo/generate")
def generate_memo(
    tz_number: Optional[str] = None,
    request_number: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Генерация данных для служебной записки"""
    if not is_sue_admin(user):
        raise HTTPException(403, "Только СУЭ может формировать служебки")
    
    if tz_number:
        items = db.query(PUItem).filter(PUItem.tz_number == tz_number).all()
        doc_type = "ТЗ"
        doc_number = tz_number
    elif request_number:
        items = db.query(PUItem).filter(PUItem.request_number == request_number).all()
        doc_type = "Заявка"
        doc_number = request_number
    else:
        raise HTTPException(400, "Укажите номер ТЗ или заявки")
    
    if not items:
        raise HTTPException(404, "ПУ не найдены")
    
    # Группируем по РЭС/ЭСК
    units_data = {}
    for item in items:
        unit_name = item.current_unit.name if item.current_unit else "Не указано"
        if unit_name not in units_data:
            units_data[unit_name] = []
        units_data[unit_name].append({
            "serial_number": item.serial_number,
            "pu_type": item.pu_type,
            "contract_number": item.contract_number,
            "consumer": item.consumer,
            "address": item.address,
            "power": item.power
        })
    
    return {
        "doc_type": doc_type,
        "doc_number": doc_number,
        "date": datetime.utcnow().strftime("%d.%m.%Y"),
        "total_count": len(items),
        "units": units_data
    }

# ==================== API: ИМПОРТ ДАННЫХ ИЗ EXCEL ====================

@app.post("/api/pu/import-techpris")
async def import_techpris_data(file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Импорт данных Техприс по номеру договора"""
    contents = await file.read()
    xl = pd.ExcelFile(io.BytesIO(contents))
    df = pd.read_excel(xl, header=None)
    
    # Ищем заголовки
    header_row = None
    cols = {}
    
    for idx, row in df.iterrows():
        for col_idx, cell in enumerate(row):
            cell_str = str(cell).lower().strip()
            if 'номер договора' in cell_str or 'договор' in cell_str:
                cols['contract'] = col_idx
                header_row = idx
            elif 'потребитель' in cell_str:
                cols['consumer'] = col_idx
            elif 'адрес' in cell_str and 'объект' in cell_str:
                cols['address'] = col_idx
            elif 'pmax' in cell_str or 'мощность' in cell_str:
                cols['power'] = col_idx
            elif 'дата заключения' in cell_str:
                cols['contract_date'] = col_idx
            elif 'планируемая дата' in cell_str or 'дата исполнения' in cell_str:
                cols['plan_date'] = col_idx
        if header_row is not None and len(cols) >= 2:
            break
    
    if 'contract' not in cols:
        raise HTTPException(400, "Не найдена колонка 'Номер договора'")
    
    # Читаем данные после заголовка
    data_rows = df.iloc[header_row + 1:].reset_index(drop=True)
    
    # Строим словарь: номер договора -> данные
    import_data = {}
    for _, row in data_rows.iterrows():
        contract = str(row.iloc[cols['contract']]).strip() if cols.get('contract') is not None else None
        if not contract or contract == 'nan' or len(contract) < 10:
            continue
        
        # Нормализуем формат договора
        contract_clean = re.sub(r'[^\d]', '', contract)
        if len(contract_clean) >= 16:
            contract_formatted = f"{contract_clean[:5]}-{contract_clean[5:7]}-{contract_clean[7:15]}-{contract_clean[15:16]}"
        else:
            contract_formatted = contract
        
        import_data[contract_formatted] = {
            'consumer': str(row.iloc[cols['consumer']]).strip() if cols.get('consumer') is not None else None,
            'address': str(row.iloc[cols['address']]).strip() if cols.get('address') is not None else None,
            'power': row.iloc[cols['power']] if cols.get('power') is not None else None,
            'contract_date': row.iloc[cols['contract_date']] if cols.get('contract_date') is not None else None,
            'plan_date': row.iloc[cols['plan_date']] if cols.get('plan_date') is not None else None,
        }
    
    # Обновляем ПУ
    updated = 0
    items = db.query(PUItem).filter(
        PUItem.status == PUStatus.TECHPRIS,
        PUItem.contract_number != None
    ).all()
    
    for item in items:
        if item.contract_number in import_data:
            data = import_data[item.contract_number]
            if data['consumer'] and data['consumer'] != 'nan':
                item.consumer = data['consumer']
            if data['address'] and data['address'] != 'nan':
                item.address = data['address']
            if data['power'] and str(data['power']) != 'nan':
                try:
                    item.power = float(data['power'])
                except:
                    pass
            if data['contract_date'] and str(data['contract_date']) != 'nan':
                try:
                    if isinstance(data['contract_date'], pd.Timestamp):
                        item.contract_date = data['contract_date'].date()
                    elif isinstance(data['contract_date'], datetime):
                        item.contract_date = data['contract_date'].date()
                except:
                    pass
            if data['plan_date'] and str(data['plan_date']) != 'nan':
                try:
                    if isinstance(data['plan_date'], pd.Timestamp):
                        item.plan_date = data['plan_date'].date()
                    elif isinstance(data['plan_date'], datetime):
                        item.plan_date = data['plan_date'].date()
                except:
                    pass
            updated += 1
    
    db.commit()
    return {"updated": updated, "total_in_file": len(import_data)}


@app.post("/api/pu/import-zamena")
async def import_zamena_data(file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Импорт данных Замена/ИЖЦ по номеру счётчика"""
    contents = await file.read()
    xl = pd.ExcelFile(io.BytesIO(contents))
    df = pd.read_excel(xl, header=None)
    
    # Ищем заголовки
    cols = {}
    header_row = None
    
    for idx, row in df.iterrows():
        for col_idx, cell in enumerate(row):
            cell_str = str(cell).lower().strip()
            if 'номер счетчика' in cell_str or 'номер пу' in cell_str or 'заводской' in cell_str:
                cols['serial'] = col_idx
                header_row = idx
            elif 'лс' in cell_str or 'лицевой' in cell_str:
                cols['ls'] = col_idx
        if header_row is not None and 'serial' in cols:
            break
    
    if 'serial' not in cols:
        raise HTTPException(400, "Не найдена колонка 'Номер счетчика'")
    if 'ls' not in cols:
        raise HTTPException(400, "Не найдена колонка 'ЛС'")
    
    # Читаем данные
    data_rows = df.iloc[header_row + 1:].reset_index(drop=True)
    
    # Строим словарь: номер счётчика -> ЛС
    import_data = {}
    for _, row in data_rows.iterrows():
        serial = str(row.iloc[cols['serial']]).strip()
        ls = str(row.iloc[cols['ls']]).strip()
        if serial and serial != 'nan' and ls and ls != 'nan':
            import_data[serial] = ls
    
    # Обновляем ПУ
    updated = 0
    items = db.query(PUItem).filter(
        PUItem.status.in_([PUStatus.ZAMENA, PUStatus.IZHC])
    ).all()
    
    for item in items:
        if item.serial_number in import_data:
            item.ls_number = import_data[item.serial_number]
            updated += 1
    
    db.commit()
    return {"updated": updated, "total_in_file": len(import_data)}


@app.post("/api/pu/import-lookup-techpris")
async def import_lookup_techpris(
    file: UploadFile = File(...),
    contract_number: str = Form(...),
    current_user: User = Depends(get_current_user)
):
    """Поиск данных по номеру договора в Excel файле"""
    content = await file.read()
    df = pd.read_excel(io.BytesIO(content), header=None)
    
    # Ищем строку с заголовками
    header_row = None
    for idx, row in df.iterrows():
        for cell in row.values:
            if 'номер договора' in str(cell).lower():
                header_row = idx
                break
        if header_row is not None:
            break
    
    if header_row is None:
        return {"found": False, "error": "Заголовок не найден"}
    
    # Переименовываем колонки
    df.columns = df.iloc[header_row]
    df = df.iloc[header_row + 1:].reset_index(drop=True)
    
    # Ищем нужные колонки
    col_map = {}
    for col in df.columns:
        col_str = str(col).strip().lower() if pd.notna(col) else ''
        if 'номер договора' in col_str:
            col_map['contract'] = col
        elif 'потребитель' in col_str:
            col_map['consumer'] = col
        elif 'адрес' in col_str:
            col_map['address'] = col
        elif 'pmax' in col_str:
            col_map['power'] = col
        elif 'p(запраш' in col_str:
            col_map['power_req'] = col
        elif 'дата заключения' in col_str:
            col_map['contract_date'] = col
        elif 'планируемая дата' in col_str:
            col_map['plan_date'] = col
    
    if 'contract' not in col_map:
        return {"found": False}
    
    # Нормализуем номер договора
    contract_clean = contract_number.replace('-', '').replace(' ', '').lower()
    
    for idx, row in df.iterrows():
        cell_value = str(row.get(col_map['contract'], '')).replace('-', '').replace(' ', '').lower()
        if not cell_value or cell_value == 'nan' or len(cell_value) < 10:
            continue
        
        if contract_clean == cell_value or contract_clean in cell_value:
            result = {"found": True}
            
            if 'consumer' in col_map:
                val = row.get(col_map['consumer'])
                if pd.notna(val) and str(val) != 'nan':
                    result['consumer'] = str(val).strip()
            
            if 'address' in col_map:
                val = row.get(col_map['address'])
                if pd.notna(val) and str(val) != 'nan':
                    result['address'] = str(val).strip()
            
            power_col = col_map.get('power_req') or col_map.get('power')
            if power_col:
                val = row.get(power_col)
                if pd.notna(val) and str(val) != 'nan':
                    try:
                        result['power'] = float(val)
                    except:
                        pass
            
            if 'contract_date' in col_map:
                val = row.get(col_map['contract_date'])
                if pd.notna(val) and str(val) != 'nan':
                    try:
                        if hasattr(val, 'strftime'):
                            result['contract_date'] = val.strftime('%Y-%m-%d')
                        else:
                            result['contract_date'] = str(val)[:10]
                    except:
                        pass
            
            if 'plan_date' in col_map:
                val = row.get(col_map['plan_date'])
                if pd.notna(val) and str(val) != 'nan':
                    try:
                        if hasattr(val, 'strftime'):
                            result['plan_date'] = val.strftime('%Y-%m-%d')
                        else:
                            result['plan_date'] = str(val)[:10]
                    except:
                        pass
            
            return result
    
    return {"found": False}


@app.post("/api/pu/import-lookup-zamena")
async def import_lookup_zamena(
    file: UploadFile = File(...),
    serial_number: str = Form(...),
    current_user: User = Depends(get_current_user)
):
    """Поиск ЛС по серийному номеру счётчика в выгрузке 1С"""
    content = await file.read()
    df = pd.read_excel(io.BytesIO(content), header=None)
    
    # Ищем колонки с заголовками "Номер счетчика" и "ЛС / ЛС СТЕК"
    col_serial = None
    col_ls = None
    header_row = None
    
    # Проходим первые 10 строк в поисках заголовков
    for idx in range(min(10, len(df))):
        row = df.iloc[idx]
        for col_idx, cell in enumerate(row.values):
            cell_str = str(cell).lower().strip() if pd.notna(cell) else ''
            if 'номер счетчика' in cell_str or 'номер счётчика' in cell_str:
                col_serial = col_idx
                header_row = idx
            elif 'лс' in cell_str and ('стек' in cell_str or col_idx < 10):
                col_ls = col_idx
    
    if col_serial is None:
        return {"found": False, "error": "Колонка 'Номер счетчика' не найдена"}
    if col_ls is None:
        return {"found": False, "error": "Колонка 'ЛС / ЛС СТЕК' не найдена"}
    
    # Нормализуем серийный номер для поиска
    serial_clean = serial_number.strip().lower()
    
    # Ищем в данных (после заголовка)
    for idx in range(header_row + 1, len(df)):
        row = df.iloc[idx]
        cell_value = str(row.iloc[col_serial]).strip().lower() if pd.notna(row.iloc[col_serial]) else ''
        
        # Пропускаем пустые
        if not cell_value or cell_value == 'nan':
            continue
        
        # Сравниваем (точное совпадение или содержит)
        if serial_clean == cell_value or serial_clean in cell_value or cell_value in serial_clean:
            ls_val = row.iloc[col_ls]
            if pd.notna(ls_val) and str(ls_val) != 'nan':
                return {"found": True, "ls_number": str(ls_val).strip()}
    
    return {"found": False, "error": f"Счётчик {serial_number} не найден в файле"}

# ==================== ИНИЦИАЛИЗАЦИЯ БД ====================
def init_db():
    db = SessionLocal()
    
    # Роли
    roles = {}
    for name, code in [
        ("СУЭ Администратор", RoleCode.SUE_ADMIN),
        ("Лаборатория", RoleCode.LAB_USER),
        ("ЭСК Администратор", RoleCode.ESK_ADMIN),
        ("Пользователь РЭС", RoleCode.RES_USER),
        ("Пользователь ЭСК", RoleCode.ESK_USER),
    ]:
        r = db.query(Role).filter(Role.code == code).first()
        if not r:
            r = Role(name=name, code=code)
            db.add(r)
            db.flush()
        roles[code] = r
    
    # Подразделения
    units = {}
    
    # Первый уровень
    for name, code, utype in [
        ("Служба учета электроэнергии", "SUE", UnitType.SUE),
        ("Лаборатория", "LAB", UnitType.LAB),
        ("ЭСК", "ESK", UnitType.ESK),
    ]:
        u = db.query(Unit).filter(Unit.code == code).first()
        if not u:
            u = Unit(name=name, code=code, unit_type=utype)
            db.add(u)
            db.flush()
        units[code] = u
    
    # 7 РЭС + 7 ЭСК подразделений
    res_data = [
        ("Адлерский РЭС", "RES_ADLER", "а"),
        ("Дагомысский РЭС", "RES_DAGOMYS", "д"),
        ("Краснополянский РЭС", "RES_KRASNAYA", "к"),
        ("Лазаревский РЭС", "RES_LAZAREV", "л"),
        ("Сочинский РЭС", "RES_SOCHI", "с"),
        ("Туапсинский РЭС", "RES_TUAPSE", "т"),
        ("Хостинский РЭС", "RES_HOSTA", "х"),
    ]
    
    for res_name, res_code, short in res_data:
        res = db.query(Unit).filter(Unit.code == res_code).first()
        if not res:
            res = Unit(name=res_name, code=res_code, unit_type=UnitType.RES, short_code=short)
            db.add(res)
            db.flush()
        
        # Подразделение ЭСК
        esk_code = res_code.replace("RES_", "ESK_")
        esk_name = res_name.replace(" РЭС", " ЭСК")
        esk = db.query(Unit).filter(Unit.code == esk_code).first()
        if not esk:
            esk = Unit(name=esk_name, code=esk_code, unit_type=UnitType.ESK_UNIT, short_code=short, parent_id=units["ESK"].id)
            db.add(esk)
    
    # Тестовые пользователи
    if not db.query(User).filter(User.username == "admin").first():
        db.add(User(username="admin", password_hash=hash_password("admin123"), full_name="Администратор СУЭ", role_id=roles[RoleCode.SUE_ADMIN].id, unit_id=units["SUE"].id))
    if not db.query(User).filter(User.username == "lab").first():
        db.add(User(username="lab", password_hash=hash_password("lab123"), full_name="Оператор Лаборатории", role_id=roles[RoleCode.LAB_USER].id, unit_id=units["LAB"].id))
    if not db.query(User).filter(User.username == "esk").first():
        db.add(User(username="esk", password_hash=hash_password("esk123"), full_name="Администратор ЭСК", role_id=roles[RoleCode.ESK_ADMIN].id, unit_id=units["ESK"].id))
    
    # Тестовые ТТР для РЭС
    for i in range(1, 8):
        for ttr_type, prefix in [("OU", "ОУ"), ("OL", "ОЛ"), ("OR", "ОР")]:
            code = f"ТТР-{i} {prefix}"
            if not db.query(TTR_RES).filter(TTR_RES.code == code).first():
                db.add(TTR_RES(code=code, name=f"Типовое решение {prefix} #{i}", ttr_type=ttr_type))
    
    # Тестовые ТТР для ЭСК
    for i in range(1, 6):
        code = f"ТТР-ЭСК-{i}"
        if not db.query(TTR_ESK).filter(TTR_ESK.code == code).first():
            db.add(TTR_ESK(code=code, name=f"Типовое решение ЭСК #{i}", price=1000*i, price_with_truba=1500*i))
    
    db.commit()
    db.close()
    print("✅ БД инициализирована!")

init_db()
