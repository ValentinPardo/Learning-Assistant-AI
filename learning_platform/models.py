from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, JSON
from learning_platform.database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password_hash = Column(String)  # ✅ Agregar campo para contraseña hasheada

class LearningGoal(Base):
    __tablename__ = "goals"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    completed = Column(Boolean, default=False)

class Task(Base):
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String)
    goal_id = Column(Integer, ForeignKey("goals.id"))
    task_metadata = Column(JSON)
    completed = Column(Boolean, default=False)