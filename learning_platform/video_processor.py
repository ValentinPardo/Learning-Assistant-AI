# video_processor.py
from datetime import time
from typing import List, Dict, Any
from learning_platform.ai import process_youtube_video
import threading
import traceback

def process_single_video(url, i, results, job_id, job_manager):
    import time
    t0 = time.time()
    print(f"⏳ [Video {i+1}] Inicio procesamiento: {url}")

    try:
        print(f"🟢 [Video {i+1}] Antes de process_youtube_video")
        t_download = time.time()
        result = process_youtube_video(url)
        t_download_end = time.time()
        print(f"⏱️ [Video {i+1}] Descarga y procesamiento: {t_download_end - t_download:.2f}s")

        if result.get("success", False) and "results" in result and result["results"]:
            video_result = result["results"][0]
            results[i] = video_result

            t_webhook = time.time()
            job_manager.send_progress_webhook(job_id, {
                "video_completed": video_result,
                "current_video": i + 1,
            })
            t_webhook_end = time.time()
            print(f"⏱️ [Video {i+1}] Envío webhook: {t_webhook_end - t_webhook:.2f}s")
        else:
            error_result = {
                "url": url,
                "error": result.get("error", "Unknown error"),
                "success": False
            }
            results[i] = error_result

        job_manager.update_job(
            job_id,
            completed_items=sum(1 for r in results if r is not None),
            results=[r for r in results if r is not None]
        )
        print(f"✅ [Video {i+1}] Procesamiento total: {time.time() - t0:.2f}s")
    except Exception as e:
        import traceback
        error_result = {
            "url": url,
            "error": str(e),
            "success": False
        }
        results[i] = error_result
        job_manager.update_job(
            job_id,
            completed_items=sum(1 for r in results if r is not None),
            results=[r for r in results if r is not None]
        )
        print(f"❌ [Video {i+1}] Error: {str(e)} (total: {time.time() - t0:.2f}s)")
        traceback.print_exc()

def process_videos_worker(
    job_id: str, 
    job_manager, 
    youtube_urls: List[str], 
) -> Dict[str, Any]:
    """
    Worker function para procesar videos de YouTube
    """
    print(f"🎬 Iniciando procesamiento job {job_id}")
    n = len(youtube_urls)
    results = [None] * n
    threads = []
    
    for i, url in enumerate(youtube_urls):
        t = threading.Thread(
            target=process_single_video,
            args=(url, i, results, job_id, job_manager)
        )
        t.start()
        threads.append(t)

    for t in threads:
        t.join()  # Esperar a que todos los videos terminen

    # Resultado final
    final_results = [r for r in results if r is not None]
    return {
        "total_videos": n,
        "successful_videos": len([r for r in final_results if r.get("success", False)]),
        "failed_videos": len([r for r in final_results if not r.get("success", True)]),
        "results": final_results
    }