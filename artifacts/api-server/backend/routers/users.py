from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from models import User
from schemas import UserCreate, UserOut, UserUpdate
from auth import hash_password, require_admin

router = APIRouter(prefix="/users", tags=["users"])

VALID_ROLES = {"admin", "operator"}


def _admin_count(db: Session) -> int:
    return db.query(User).filter(User.role == "admin").count()


def _active_admin_count(db: Session) -> int:
    return db.query(User).filter(User.role == "admin", User.is_active.is_(True)).count()


@router.get("/", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return db.query(User).order_by(User.username).all()


@router.post("/", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    body: UserCreate, db: Session = Depends(get_db), _: User = Depends(require_admin)
):
    if body.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail="Invalid role")
    if not body.password:
        raise HTTPException(
            status_code=400, detail="Password is required for local accounts"
        )
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(status_code=409, detail="Username already exists")
    user = User(
        username=body.username,
        email=body.email,
        full_name=body.full_name,
        role=body.role,
        auth_provider="local",
        password_hash=hash_password(body.password),
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    body: UserUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if body.role is not None:
        if body.role not in VALID_ROLES:
            raise HTTPException(status_code=400, detail="Invalid role")
        if user.role == "admin" and body.role != "admin" and _admin_count(db) <= 1:
            raise HTTPException(status_code=400, detail="Cannot demote the last admin")
        user.role = body.role

    if body.email is not None:
        user.email = body.email
    if body.full_name is not None:
        user.full_name = body.full_name

    if body.is_active is not None:
        if (
            not body.is_active
            and user.role == "admin"
            and _active_admin_count(db) <= 1
        ):
            raise HTTPException(
                status_code=400, detail="Cannot deactivate the last admin"
            )
        user.is_active = body.is_active

    if body.password:
        user.password_hash = hash_password(body.password)

    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")
    if user.role == "admin" and _admin_count(db) <= 1:
        raise HTTPException(status_code=400, detail="Cannot delete the last admin")
    db.delete(user)
    db.commit()
    return None
