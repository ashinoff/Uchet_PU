"""
Система учета ПУ - Backend
"""
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Enum as SQLEnum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from sqlalchemy.sql import func
from pydantic import BaseModel
from pydantic_settings import BaseSettings
from typing import Optional, List
from datetime import datetime, timedelta
from jose import jwt
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import bcrypt as _bcrypt
import pandas as pd
import io
import enum

# ==================== КОНФИГ ====================
class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://user:pass@localhost/pu_system"
    SECRET_KEY: str = "your-secret-key-change-me"
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
    SUE = "SUE"          # Служба учета - видит ВСЁ
    LAB = "LAB"          # Лаборатория - загружает реестры
    ESK = "ESK"          # ЭСК (центральный) - админ всех ЭСК
    RES = "RES"          # РЭС (7 штук)
    RES_ESK = "RES_ESK"  # ЭСК в РЭС (7 штук)

class RoleCode(str, enum.Enum):
    SUE_ADMIN = "SUE_ADMIN"      # Видит всё, перемещает только РЭС
    LAB_USER = "LAB_USER"        # Загружает реестры
    ESK_ADMIN = "ESK_ADMIN"      # Видит все ЭСК, перемещает между ЭСК

class PUStatus(str, enum.Enum):
    NEW = "NEW"              # Новый
    IN_ESK = "IN_ESK"        # В ЭСК
    IN_RES = "IN_RES"        # В РЭС
    INSTALLED = "INSTALLED"  # Установлен
    DEFECT = "DEFECT"        # Брак

# ==================== МОДЕЛИ БД ====================
class Unit(Base):
    __tablename__ = "units"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    code = Column(String(50), unique=True)
    unit_type = Column(SQLEnum(UnitType))
    parent_id = Column(Integer, ForeignKey("units.id"))
    is_active = Column(Boolean, default=True)

class Role(Base):
    __tablename__ = "roles"
    id = Column(Integer, primary_key=True)
    name = Column(String(100))
    code = Column(SQLEnum(RoleCode), unique=True)

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True)
    password_hash = Column(String(255))
    full_name = Column(String(200))
    role_id = Column(Integer, ForeignKey("roles.id"))
    unit_id = Column(Integer, ForeignKey("units.id"))
    is_active = Column(Boolean, default=True)
    role = relationship("Role")
    unit = relationship("Unit")

class PURegister(Base):
    __tablename__ = "pu_registers"
    id = Column(Integer, primary_key=True)
    filename = Column(String(255))
    uploaded_by = Column(Integer, ForeignKey("users.id"))
    uploaded_at = Column(DateTime, server_default=func.now())
    items_count = Column(Integer, default=0)
    uploader = relationship("User")

class PUItem(Base):
    __tablename__ = "pu_items"
    id = Column(Integer, primary_key=True)
    register_id = Column(Integer, ForeignKey("pu_registers.id"))
    pu_type = Column(String(500))
    serial_number = Column(String(100), index=True)
    target_unit_id = Column(Integer, ForeignKey("units.id"))
    current_unit_id = Column(Integer, ForeignKey("units.id"))
    status = Column(SQLEnum(PUStatus), default=PUStatus.NEW)
    created_at = Column(DateTime, server_default=func.now())
    register = relationship("PURegister")
    target_unit = relationship("Unit", foreign_keys=[target_unit_id])
    current_unit = relationship("Unit", foreign_keys=[current_unit_id])

class PUMovement(Base):
    __tablename__ = "pu_movements"
    id = Column(Integer, primary_key=True)
    pu_item_id = Column(Integer, ForeignKey("pu_items.id"))
    from_unit_id = Column(Integer, ForeignKey("units.id"))
    to_unit_id = Column(Integer, ForeignKey("units.id"))
    moved_by = Column(Integer, ForeignKey("users.id"))
    moved_at = Column(DateTime, server_default=func.now())
    comment = Column(Text)

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

def is_sue_admin(user: User) -> bool:
    return user.role.code == RoleCode.SUE_ADMIN

def is_esk_admin(user: User) -> bool:
    return user.role.code == RoleCode.ESK_ADMIN

def is_lab_user(user: User) -> bool:
    return user.role.code == RoleCode.LAB_USER

def get_visible_units(user: User, db: Session) -> List[int]:
    """Какие подразделения видит пользователь"""
    if is_sue_admin(user):
        return [u.id for u in db.query(Unit).all()]
    if is_esk_admin(user):
        # ЭСК видит только ЭСК подразделения
        return [u.id for u in db.query(Unit).filter(Unit.unit_type.in_([UnitType.ESK, UnitType.RES_ESK])).all()]
    if is_lab_user(user):
        return [user.unit_id] if user.unit_id else []
    return []

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
    visible_units: List[int] = []

class UnitResp(BaseModel):
    id: int
    name: str
    code: str
    unit_type: str

class MoveReq(BaseModel):
    pu_item_ids: List[int]
    to_unit_id: int
    comment: Optional[str] = None

# ==================== ПРИЛОЖЕНИЕ ====================
app = FastAPI(title="Система учета ПУ")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

Base.metadata.create_all(bind=engine)

# ==================== API ENDPOINTS ====================

@app.get("/")
def root():
    return {"status": "ok", "message": "Система учета ПУ"}

# --- Auth ---
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
        unit_id=user.unit_id, unit_name=user.unit.name if user.unit else None,
        visible_units=get_visible_units(user, db)
    )

# --- Справочники ---
@app.get("/api/units", response_model=List[UnitResp])
def get_units(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    units = db.query(Unit).filter(Unit.is_active == True).all()
    return [UnitResp(id=u.id, name=u.name, code=u.code, unit_type=u.unit_type.value) for u in units]

@app.get("/api/roles")
def get_roles(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return [{"id": r.id, "name": r.name, "code": r.code.value} for r in db.query(Role).all()]

# --- Пользователи (только СУЭ) ---
@app.get("/api/users")
def get_users(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not is_sue_admin(user):
        raise HTTPException(403, "Нет доступа")
    users = db.query(User).all()
    return [{
        "id": u.id, "username": u.username, "full_name": u.full_name, "is_active": u.is_active,
        "role": {"id": u.role.id, "name": u.role.name} if u.role else None,
        "unit": {"id": u.unit.id, "name": u.unit.name} if u.unit else None
    } for u in users]

@app.post("/api/users")
def create_user(data: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not is_sue_admin(user):
        raise HTTPException(403, "Нет доступа")
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

# --- ПУ ---
@app.get("/api/pu/dashboard")
def dashboard(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    visible = get_visible_units(user, db)
    
    q = db.query(PUItem)
    if not is_sue_admin(user):
        if is_lab_user(user):
            regs = db.query(PURegister.id).filter(PURegister.uploaded_by == user.id)
            q = q.filter(PUItem.register_id.in_(regs))
        elif is_esk_admin(user):
            q = q.filter(PUItem.current_unit_id.in_(visible))
    
    total = q.count()
    in_esk = q.filter(PUItem.status == PUStatus.IN_ESK).count()
    in_res = q.filter(PUItem.status == PUStatus.IN_RES).count()
    installed = q.filter(PUItem.status == PUStatus.INSTALLED).count()
    
    reg_q = db.query(PURegister)
    if is_lab_user(user):
        reg_q = reg_q.filter(PURegister.uploaded_by == user.id)
    recent = reg_q.order_by(PURegister.uploaded_at.desc()).limit(5).all()
    
    return {
        "total_pu": total, "in_esk": in_esk, "in_res": in_res, "installed": installed,
        "recent_registers": [{"id": r.id, "filename": r.filename, "items_count": r.items_count, "uploaded_at": r.uploaded_at, "status": "completed"} for r in recent]
    }

@app.get("/api/pu/items")
def get_items(page: int = 1, size: int = 50, search: Optional[str] = None, status: Optional[str] = None, unit_id: Optional[int] = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    visible = get_visible_units(user, db)
    q = db.query(PUItem)
    
    if not is_sue_admin(user):
        if is_lab_user(user):
            regs = db.query(PURegister.id).filter(PURegister.uploaded_by == user.id)
            q = q.filter(PUItem.register_id.in_(regs))
        elif is_esk_admin(user):
            q = q.filter(PUItem.current_unit_id.in_(visible))
    
    if search:
        q = q.filter(PUItem.serial_number.ilike(f"%{search}%"))
    if status:
        q = q.filter(PUItem.status == status)
    if unit_id:
        q = q.filter(PUItem.current_unit_id == unit_id)
    
    total = q.count()
    items = q.order_by(PUItem.created_at.desc()).offset((page-1)*size).limit(size).all()
    
    return {
        "items": [{
            "id": i.id, "serial_number": i.serial_number, "pu_type": i.pu_type,
            "status": i.status.value, "current_unit_id": i.current_unit_id,
            "current_unit_name": i.current_unit.name if i.current_unit else None,
            "uploaded_at": i.register.uploaded_at if i.register else None
        } for i in items],
        "total": total, "page": page, "size": size, "pages": (total + size - 1) // size
    }

@app.get("/api/pu/registers")
def get_registers(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(PURegister)
    if is_lab_user(user):
        q = q.filter(PURegister.uploaded_by == user.id)
    elif not is_sue_admin(user):
        return []
    regs = q.order_by(PURegister.uploaded_at.desc()).all()
    return [{"id": r.id, "filename": r.filename, "items_count": r.items_count, "uploaded_at": r.uploaded_at, "status": "completed"} for r in regs]

@app.post("/api/pu/upload")
async def upload_register(file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not is_lab_user(user):
        raise HTTPException(403, "Только Лаборатория может загружать реестры")
    
    contents = await file.read()
    xl = pd.ExcelFile(io.BytesIO(contents))
    
    # Ищем лист с данными
    df = None
    for sheet in xl.sheet_names:
        temp_df = pd.read_excel(xl, sheet_name=sheet)
        for col in temp_df.columns:
            if 'заводской' in str(col).lower() or 'номер' in str(col).lower():
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
        units_map[u.code.lower()] = u
    # Короткие названия
    for u in db.query(Unit).filter(Unit.unit_type == UnitType.RES).all():
        short = u.name.lower().replace(' рэс', '').replace('ий', 'ий рэс')
        units_map[u.name.lower()] = u
    for u in db.query(Unit).filter(Unit.unit_type == UnitType.RES_ESK).all():
        units_map['эск'] = u  # последний ЭСК как дефолт для "ЭСК"
    
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
                # Пробуем найти по частичному совпадению
                if not target_unit:
                    for key, u in units_map.items():
                        if unit_name in key or key in unit_name:
                            target_unit = u
                            break
        
        status = PUStatus.NEW
        if target_unit:
            if target_unit.unit_type in [UnitType.ESK, UnitType.RES_ESK]:
                status = PUStatus.IN_ESK
            elif target_unit.unit_type == UnitType.RES:
                status = PUStatus.IN_RES
        
        item = PUItem(
            register_id=register.id, pu_type=pu_type[:500] if pu_type else None,
            serial_number=serial, target_unit_id=target_unit.id if target_unit else None,
            current_unit_id=target_unit.id if target_unit else None, status=status
        )
        db.add(item)
        count += 1
    
    register.items_count = count
    db.commit()
    return {"id": register.id, "filename": register.filename, "items_count": count, "uploaded_at": register.uploaded_at, "status": "completed"}

@app.post("/api/pu/move")
def move_items(req: MoveReq, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    target = db.query(Unit).filter(Unit.id == req.to_unit_id).first()
    if not target:
        raise HTTPException(404, "Подразделение не найдено")
    
    items = db.query(PUItem).filter(PUItem.id.in_(req.pu_item_ids)).all()
    
    # Проверка прав
    if is_sue_admin(user):
        # СУЭ может перемещать только ПУ которые НЕ в ЭСК
        for item in items:
            if item.current_unit and item.current_unit.unit_type in [UnitType.ESK, UnitType.RES_ESK]:
                raise HTTPException(403, "СУЭ не может перемещать ПУ из ЭСК")
        # И только в РЭС (не в ЭСК)
        if target.unit_type in [UnitType.ESK, UnitType.RES_ESK]:
            raise HTTPException(403, "СУЭ может перемещать только в РЭС")
    elif is_esk_admin(user):
        # ЭСК может перемещать только ПУ из ЭСК
        for item in items:
            if item.current_unit and item.current_unit.unit_type not in [UnitType.ESK, UnitType.RES_ESK]:
                raise HTTPException(403, "ЭСК может перемещать только ПУ из ЭСК")
        # И только в ЭСК
        if target.unit_type not in [UnitType.ESK, UnitType.RES_ESK]:
            raise HTTPException(403, "ЭСК может перемещать только в ЭСК")
    else:
        raise HTTPException(403, "Нет прав на перемещение")
    
    for item in items:
        mov = PUMovement(pu_item_id=item.id, from_unit_id=item.current_unit_id, to_unit_id=target.id, moved_by=user.id, comment=req.comment)
        db.add(mov)
        item.current_unit_id = target.id
        item.status = PUStatus.IN_ESK if target.unit_type in [UnitType.ESK, UnitType.RES_ESK] else PUStatus.IN_RES
    
    db.commit()
    return {"moved": len(items)}

@app.post("/api/pu/delete")
def delete_items(data: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not is_sue_admin(user):
        raise HTTPException(403, "Нет прав на удаление")
    
    # Проверка кода админа
    if data.get("admin_code") != "2233":
        raise HTTPException(403, "Неверный код администратора")
    
    item_ids = data.get("pu_item_ids", [])
    if not item_ids:
        raise HTTPException(400, "Не выбраны ПУ")
    
    # Удаляем перемещения
    db.query(PUMovement).filter(PUMovement.pu_item_id.in_(item_ids)).delete(synchronize_session=False)
    
    # Удаляем ПУ
    deleted = db.query(PUItem).filter(PUItem.id.in_(item_ids)).delete(synchronize_session=False)
    
    db.commit()
    return {"deleted": deleted}

# ==================== ИНИЦИАЛИЗАЦИЯ БД ====================
def init_db():
    db = SessionLocal()
    
    # Роли (3 штуки)
    roles = {}
    for name, code in [("СУЭ Администратор", RoleCode.SUE_ADMIN), ("Лаборатория", RoleCode.LAB_USER), ("ЭСК Администратор", RoleCode.ESK_ADMIN)]:
        r = db.query(Role).filter(Role.code == code).first()
        if not r:
            r = Role(name=name, code=code)
            db.add(r)
            db.flush()
        roles[code] = r
    
    # Подразделения
    units = {}
    
    # Служебные
    for name, code, utype in [("Служба учета", "SUE", UnitType.SUE), ("Лаборатория", "LAB", UnitType.LAB), ("ЭСК", "ESK", UnitType.ESK)]:
        u = db.query(Unit).filter(Unit.code == code).first()
        if not u:
            u = Unit(name=name, code=code, unit_type=utype)
            db.add(u)
            db.flush()
        units[code] = u
    
    # 7 РЭС + 7 ЭСК
    for res_name, res_code in [
        ("Адлерский РЭС", "RES_ADLER"), ("Дагомысский РЭС", "RES_DAGOMYS"), ("Краснополянский РЭС", "RES_KRASNAYA"),
        ("Лазаревский РЭС", "RES_LAZAREV"), ("Сочинский РЭС", "RES_SOCHI"), ("Туапсинский РЭС", "RES_TUAPSE"), ("Хостинский РЭС", "RES_HOSTA")
    ]:
        res = db.query(Unit).filter(Unit.code == res_code).first()
        if not res:
            res = Unit(name=res_name, code=res_code, unit_type=UnitType.RES)
            db.add(res)
            db.flush()
        
        # ЭСК в РЭС
        esk_code = res_code.replace("RES_", "ESK_")
        esk_name = res_name.replace(" РЭС", " ЭСК")
        esk = db.query(Unit).filter(Unit.code == esk_code).first()
        if not esk:
            esk = Unit(name=esk_name, code=esk_code, unit_type=UnitType.RES_ESK, parent_id=res.id)
            db.add(esk)
    
    # Пользователи
    if not db.query(User).filter(User.username == "admin").first():
        db.add(User(username="admin", password_hash=hash_password("admin123"), full_name="Администратор СУЭ", role_id=roles[RoleCode.SUE_ADMIN].id, unit_id=units["SUE"].id))
    if not db.query(User).filter(User.username == "lab").first():
        db.add(User(username="lab", password_hash=hash_password("lab123"), full_name="Оператор Лаборатории", role_id=roles[RoleCode.LAB_USER].id, unit_id=units["LAB"].id))
    if not db.query(User).filter(User.username == "esk").first():
        db.add(User(username="esk", password_hash=hash_password("esk123"), full_name="Администратор ЭСК", role_id=roles[RoleCode.ESK_ADMIN].id, unit_id=units["ESK"].id))
    
    db.commit()
    db.close()
    print("✅ БД инициализирована!")

init_db()
