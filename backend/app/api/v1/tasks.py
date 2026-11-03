"""Task CRUD endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.models import Task
from app.schemas.schemas import TaskCreate, TaskRead, TaskUpdate
from app.core.config import settings

router = APIRouter()


def _get_demo_user_id() -> str:
    return settings.demo_user_id


@router.get("", response_model=list[TaskRead])
def list_tasks(db: Session = Depends(get_db)):
    user_id = _get_demo_user_id()
    return db.query(Task).filter(Task.user_id == user_id).all()


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
def create_task(payload: TaskCreate, db: Session = Depends(get_db)):
    user_id = _get_demo_user_id()
    task = Task(user_id=user_id, **payload.model_dump())
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@router.put("/{task_id}", response_model=TaskRead)
def update_task(task_id: str, payload: TaskUpdate, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if not task or task.user_id != _get_demo_user_id():
        raise HTTPException(404, "Task not found")
    for k, v in payload.model_dump(exclude_none=True).items():
        setattr(task, k, v)
    db.commit()
    db.refresh(task)
    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: str, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if not task or task.user_id != _get_demo_user_id():
        raise HTTPException(404, "Task not found")
    db.delete(task)
    db.commit()
