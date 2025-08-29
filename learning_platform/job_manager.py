# job_manager.py
import uuid
import threading
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Callable
from enum import Enum
from learning_platform.schema import ProcessingStatus

class JobManager:
    """Gestor de trabajos asíncronos en memoria"""
    
    def __init__(self):
        self.storage = {}
        self.active_threads = {}
    
    def create_job(
        self, 
        job_type: str,
        #user_id: int,
        job_data: Dict[str, Any],
        webhook_url: Optional[str] = None
    ) -> str:
        """
        Crear un nuevo job
        
        Args:
            job_type: Tipo de trabajo (ej: 'video_processing', 'data_export', etc.)
            user_id: ID del usuario propietario
            job_data: Datos específicos del trabajo
            webhook_url: URL para notificaciones
        """
        job_id = str(uuid.uuid4())
        
        self.storage[job_id] = {
            "id": job_id,
            "type": job_type,
            "status": ProcessingStatus.PENDING,
            #"user_id": user_id,
            "data": job_data,
            "webhook_url": webhook_url,
            "progress": {
                "total_items": job_data.get("total_items", 0),
                "completed_items": 0,
                "percentage": 0
            },
            "results": [],
            "error": None,
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
            "metadata": {}
        }
        
        return job_id
    
    def get_job(self, job_id: str) -> Optional[Dict]:
        """Obtener información de un job"""
        return self.storage.get(job_id)
    
    
    def delete_job(self, job_id: str) -> bool:
        """Eliminar un job"""
        if job_id in self.storage:
            del self.storage[job_id]
            return True
        return False
    
    def execute_job_async(
        self, 
        job_id: str, 
        worker_function: Callable,
        *args,
        **kwargs
    ) -> bool:
        """
        Ejecutar un job en background usando threading
        
        Args:
            job_id: ID del job
            worker_function: Función que procesará el job
            *args, **kwargs: Argumentos para la función worker
        """
        if job_id not in self.storage:
            return False
        
        # Marcar como procesando
        self.update_job(job_id, status=ProcessingStatus.PROCESSING)
        
        # Crear y ejecutar thread
        thread = threading.Thread(
            target=self._execute_worker,
            args=(job_id, worker_function, args, kwargs),
            daemon=True
        )
        
        self.active_threads[job_id] = thread
        thread.start()
        
        return True
    
    def _execute_worker(
        self, 
        job_id: str, 
        worker_function: Callable,
        args: tuple,
        kwargs: dict
    ):
        """Ejecutar función worker y manejar estados"""
        try:
            # Ejecutar función worker
            result = worker_function(job_id, self, *args, **kwargs)
            
            # Marcar como completado
            self.update_job(
                job_id,
                status=ProcessingStatus.COMPLETED,
                final_result=result
            )
            
            # Enviar notificación de completado
            self._send_completion_webhook(job_id)
            
        except Exception as e:
            # Marcar como fallido
            self.update_job(
                job_id,
                status=ProcessingStatus.FAILED,
                error=str(e)
            )
            
            # Enviar notificación de error
            self._send_error_webhook(job_id, str(e))
        
        finally:
            # Limpiar thread activo
            if job_id in self.active_threads:
                del self.active_threads[job_id]
    
    def _send_completion_webhook(self, job_id: str):
        """Enviar webhook de job completado"""
        job = self.get_job(job_id)
        if not job or not job.get("webhook_url"):
            return
        
        payload = {
            "type": "job_completed",
            "job_id": job_id,
            "job_type": job["type"],
            #"user_id": job["user_id"],
            "status": job["status"],
            "progress": job["progress"],
            "results": job["results"],
            "timestamp": datetime.now().isoformat()
        }
        
        self._send_webhook(job["webhook_url"], payload)
    
    def _send_error_webhook(self, job_id: str, error: str):
        """Enviar webhook de error"""
        job = self.get_job(job_id)
        if not job or not job.get("webhook_url"):
            return
        
        payload = {
            "type": "job_failed",
            "job_id": job_id,
            "job_type": job["type"],
           #"user_id": job["user_id"],
            "error": error,
            "timestamp": datetime.now().isoformat()
        }
        
        self._send_webhook(job["webhook_url"], payload)
    
    def send_progress_webhook(self, job_id: str, data: Dict[str, Any]):
        """Enviar webhook de progreso"""
        job = self.get_job(job_id)
        if not job or not job.get("webhook_url"):
            return
        
        payload = {
            "type": "job_progress",
            "job_id": job_id,
            "job_type": job["type"],
           #"user_id": job["user_id"],
            "progress": job["progress"],
            "data": data,
            "timestamp": datetime.now().isoformat()
        }
        
        self._send_webhook(job["webhook_url"], payload)
    
    def _send_webhook(self, webhook_url: str, payload: Dict[str, Any]):
        """Enviar payload al webhook"""
        try:
            response = requests.post(
                webhook_url,
                json=payload,
                timeout=30,
                headers={"Content-Type": "application/json"}
            )
            print(f"📤 Webhook enviado: {response.status_code}")
        except Exception as e:
            print(f"❌ Error enviando webhook: {e}")
    
    def get_active_jobs(self) -> List[str]:
        """Obtener lista de jobs activos"""
        return list(self.active_threads.keys())
    
    def cleanup_old_jobs(self, days: int = 7):
        """Limpiar jobs antiguos (para evitar memory leaks)"""
        cutoff_date = datetime.now() - timedelta(days=days)
        jobs_to_delete = []
        
        for job_id, job_data in self.storage.items():
            if job_data["updated_at"] < cutoff_date:
                jobs_to_delete.append(job_id)
        
        for job_id in jobs_to_delete:
            self.delete_job(job_id)
        
        return len(jobs_to_delete)

    # FUNCIONES NO UTILIZADAS
    def update_job(self, job_id: str, **kwargs) -> bool:
        """Actualizar datos de un job"""
        if job_id not in self.storage:
            return False
            
        self.storage[job_id].update(kwargs)
        self.storage[job_id]["updated_at"] = datetime.now()
        
        # Actualizar progreso automáticamente
        if "completed_items" in kwargs:
            total = self.storage[job_id]["progress"]["total_items"]
            completed = kwargs["completed_items"]
            if total > 0:
                percentage = (completed / total) * 100
                self.storage[job_id]["progress"]["percentage"] = percentage
        
        return True

    def get_user_jobs(self, user_id: int, job_type: Optional[str] = None) -> List[Dict]:
        """Obtener todos los jobs de un usuario"""
        user_jobs = []
        for job_id, job_data in self.storage.items():
            if job_data.get("user_id") == user_id:
                if job_type is None or job_data.get("type") == job_type:
                    user_jobs.append(job_data)
        return user_jobs


# Instancia global del job manager
job_manager = JobManager()