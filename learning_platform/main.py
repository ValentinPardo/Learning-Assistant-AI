from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta
from learning_platform.models import *
from learning_platform.schema import *
from learning_platform.database import SessionLocal, engine
from learning_platform.auth import authenticate_user, create_access_token, get_current_user, get_password_hash, ACCESS_TOKEN_EXPIRE_MINUTES
from learning_platform.job_manager import job_manager
from learning_platform.video_processor import process_videos_worker
from learning_platform.schema import ProcessingStatus
from typing import List, Dict, Any
# Base.metadata.drop_all(bind=engine)
# Crear las tablas
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Learning Platform API")

# Dependency para obtener la sesión de BD
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

#=======================
# AUTHENTICATION
#=======================
@app.post("/register/oauth", response_model=UserResponse)
async def register_user(user: UserAuth, db: Session = Depends(get_db)):
    """Registrar nuevo usuario"""
    # Verificar si el usuario ya existe
    existing_user = db.query(User).filter(User.username == user.username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Username already exists")
    
    # Hashear la contraseña
    hashed_password = get_password_hash(user.password)
    
    # Crear usuario con contraseña hasheada
    db_user = User(username=user.username, password_hash=hashed_password)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

@app.post("/login/oauth", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """Login OAuth2 estándar"""
    user = authenticate_user(form_data.username, form_data.password, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user["username"], "user_id": user["user_id"]}, 
        expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/oauth/me")
async def read_users_me(current_user: dict = Depends(get_current_user)):
    """Obtener información del usuario autenticado"""
    return {
        "username": current_user["username"],
        "user_id": current_user["user_id"],
        "message": "Usuario autenticado correctamente"
    }

#=======================
# GETS
#=======================
@app.get("/")
async def root():
    return {"message": "Learning Platform API"}

@app.get("/users", response_model=list[UserResponse])
async def get_users(db: Session = Depends(get_db)):
    users = db.query(User).all()
    return users

@app.get("/goals", response_model=list[LearningGoalResponse])
async def get_goals(db: Session = Depends(get_db)):
    goals = db.query(LearningGoal).all()
    return goals

@app.get("/tasks", response_model=list[TaskResponse])
async def get_tasks(db: Session = Depends(get_db)):
    tasks = db.query(Task).all()
    return tasks

#=======================
# GETS PROTEGIDOS
#=======================
@app.get("/my/goals", response_model=list[LearningGoalResponse])
async def get_my_goals(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Obtener goals del usuario autenticado"""
    goals = db.query(LearningGoal).filter(
        LearningGoal.user_id == current_user["user_id"]
    ).all()
    return goals

@app.get("/my/goals/{goal_id}/tasks", response_model=list[TaskResponse])
async def get_my_goal_tasks(
    goal_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Obtener tasks de un goal del usuario autenticado"""
    # Verificar que el goal pertenece al usuario
    goal = db.query(LearningGoal).filter(
        LearningGoal.id == goal_id,
        LearningGoal.user_id == current_user["user_id"]
    ).first()
    
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    
    tasks = db.query(Task).filter(Task.goal_id == goal_id).all()
    return tasks

#=======================
# POSTS PROTEGIDOS
#=======================
@app.post("/my/goals", response_model=LearningGoalResponse)
async def create_my_learning_goal(
    goal: LearningGoalCreate, 
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Crear goal para el usuario autenticado"""
    db_goal = LearningGoal(
        title=goal.title,
        user_id=current_user["user_id"]  #Del token JWT, no del parámetro
    )
    db.add(db_goal)
    db.commit()
    db.refresh(db_goal)
    return db_goal

@app.post("/my/goals/{goal_id}/tasks", response_model=TaskResponse)
async def create_my_task(
    goal_id: int,
    task: TaskCreate, 
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Crear task en un goal del usuario autenticado"""
    # Verificar que el goal pertenece al usuario autenticado
    goal = db.query(LearningGoal).filter(
        LearningGoal.id == goal_id,
        LearningGoal.user_id == current_user["user_id"]  # Verificación de ownership
    ).first()
    
    if not goal:
        raise HTTPException(
            status_code=404, 
            detail="Goal not found or you don't have permission"
        )
    
    try:
        db_task = Task(
            goal_id=goal_id, 
            title=task.title, 
            task_metadata=task.task_metadata
        )
        db.add(db_task)
        db.commit()
        db.refresh(db_task)
        return db_task
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    
#=======================
# POST FOR AI
#=======================
@app.post("/ai/process-videos", response_model=VideoProcessAsyncResponse)
async def process_videos_async(
    request: VideoProcessRequest,
    #current_user: dict = Depends(get_current_user),
    #db: Session = Depends(get_db)
):
    """
    Iniciar procesamiento asíncrono de videos de YouTube
    Retorna inmediatamente con job_id para seguimiento
    """
    try:
        # Validar URLs
        if not request.youtube_urls:
            raise HTTPException(status_code=400, detail="No se proporcionaron URLs")
        
        if len(request.youtube_urls) > 10:
            raise HTTPException(status_code=400, detail="Máximo 10 videos por request")
        
        # Configurar webhook
        webhook_url = request.webhook_url or "https://pardinian.app.n8n.cloud/webhook-test/09484a9c-bccb-4344-8f11-957aed42daef"
        
        # Crear job usando el job manager
        job_id = job_manager.create_job(
            job_type="video_processing",
            #user_id=current_user["user_id"],
            job_data={
                "youtube_urls": request.youtube_urls,
                "total_items": len(request.youtube_urls)
            },
            webhook_url=webhook_url
        )
        
        # Ejecutar procesamiento asíncrono
        job_manager.execute_job_async(
            job_id,
            process_videos_worker,
            request.youtube_urls,
            webhook_url
        )
        
        # Retornar inmediatamente
        return VideoProcessAsyncResponse(
            message="Procesamiento iniciado exitosamente",
            job_id=job_id,
            status=ProcessingStatus.PENDING,
            total_videos=len(request.youtube_urls),
            estimated_time_minutes=len(request.youtube_urls) * 2
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error iniciando procesamiento: {e}")
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")

#=======================
# GET PARA ESTADO DEL JOB
#=======================
@app.get("/ai/jobs/{job_id}/status", response_model=VideoProcessStatusResponse)
async def get_job_status(
    job_id: str,
    current_user: dict = Depends(get_current_user),
    #db: Session = Depends(get_db)
):
    """Obtener estado del procesamiento de videos"""
    job = job_manager.get_job(job_id)
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Verificar que el job pertenece al usuario
    if job.get("user_id") != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    return VideoProcessStatusResponse(
        job_id=job_id,
        status=job["status"],
        progress={
            "percentage": job["progress"]["percentage"],
            "current_video": job["progress"]["completed_items"],
            "estimated_remaining_minutes": (job["progress"]["total_items"] - job["progress"]["completed_items"]) * 2
        },
        completed_videos=job["progress"]["completed_items"],
        total_videos=job["progress"]["total_items"],
        results=job["results"],
        error=job.get("error")
    )

@app.get("/ai/jobs", response_model=List[VideoProcessStatusResponse])
async def get_my_jobs(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Obtener todos los jobs del usuario autenticado"""
    user_jobs = job_manager.get_user_jobs(current_user["user_id"], "video_processing")
    
    response_jobs = []
    for job in user_jobs:
        response_jobs.append(VideoProcessStatusResponse(
            job_id=job["id"],
            status=job["status"],
            progress={
                "percentage": job["progress"]["percentage"],
                "current_video": job["progress"]["completed_items"]
            },
            completed_videos=job["progress"]["completed_items"],
            total_videos=job["progress"]["total_items"],
            results=job["results"],
            error=job.get("error")
        ))
    
    return response_jobs

#=======================
# PUTS PROTEGIDO
#=======================

def check_and_complete_goal(goal_id: int, db: Session):
    """Verificar si todas las tasks están completadas y marcar el goal como completado"""
    # Contar tasks totales del goal
    total_tasks = db.query(Task).filter(Task.goal_id == goal_id).count()
    
    # Si no hay tasks, no completar el goal automáticamente
    if total_tasks == 0:
        return False
    
    # Contar tasks completadas del goal
    completed_tasks = db.query(Task).filter(
        Task.goal_id == goal_id,
        Task.completed == True
    ).count()
    
    # Si todas las tasks están completadas, marcar goal como completado
    if total_tasks == completed_tasks:
        goal = db.query(LearningGoal).filter(LearningGoal.id == goal_id).first()
        goal.completed = True
        db.commit()
        return True
    
    # Si hay tasks incompletas, marcar goal como incompleto
    else:
        goal = db.query(LearningGoal).filter(LearningGoal.id == goal_id).first()
        if goal.completed:
            goal.completed = False
            db.commit()
    
    return False

@app.put("/my/goals/{goal_id}/tasks/{task_id}", response_model=TaskUpdateResponse)
async def update_my_task(
    goal_id: int,
    task_id: int, 
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Actualizar una task en un goal del usuario autenticado"""
    # Verificar que el goal pertenece al usuario
    goal = db.query(LearningGoal).filter(
        LearningGoal.id == goal_id,
        LearningGoal.user_id == current_user["user_id"]
    ).first()
    
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found or you don't have permission")
    
    # Obtener la task
    db_task = db.query(Task).filter(
        Task.id == task_id,
        Task.goal_id == goal_id
    ).first()

    if not db_task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Actualizar task
    db_task.completed = True
    db.commit()
    db.refresh(db_task)
    
    goal_completed = check_and_complete_goal(goal_id, db)
    
    return TaskUpdateResponse(
        id=db_task.id,
        title=db_task.title,
        goal_id=db_task.goal_id,
        completed=db_task.completed,
        task_metadata=db_task.task_metadata or {},
        goal_auto_completed=goal_completed
    )
#=======================
# DELETES
#=======================
@app.delete("/my/goals/{goal_id}")
async def delete_goal(
    goal_id: int, 
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a goal that belongs to the authenticated user"""
    goal = db.query(LearningGoal).filter(
        LearningGoal.id == goal_id,
        LearningGoal.user_id == current_user["user_id"]  # Ensure goal belongs to user
    ).first()
    
    if not goal:
        raise HTTPException(
            status_code=404, 
            detail="Goal not found or you don't have permission"
        )
    
    try:
        # First delete all associated tasks
        db.query(Task).filter(Task.goal_id == goal_id).delete()
        # Then delete the goal
        db.delete(goal)
        db.commit()
        return {"message": "Goal and all associated tasks deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


#==============================
# DELETE ALL TASKS FOR DEBUG
# =============================
    
@app.delete("/all")
async def delete_all(db: Session = Depends(get_db)):
    try:
        db.query(Task).delete()
        db.query(LearningGoal).delete()
        db.query(User).delete()
        db.commit()
        return {"message": "All data deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    
