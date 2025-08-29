# ai.py
import os
import yt_dlp
import whisper
import requests
from langchain_google_genai import GoogleGenerativeAI
from langchain.chains.summarize import load_summarize_chain
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.prompts import PromptTemplate
import subprocess
from typing import List, Dict, Any

# Configuración inicial
os.environ["GOOGLE_API_KEY"] = "AIzaSyD6LmHAzx18M5B6sksVVOShR7I1zvGQUTA"

def check_dependencies():
    """Verificar dependencias requeridas"""
    try:
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, check=True)
        print("✅ FFmpeg está disponible")
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("❌ FFmpeg no está disponible")
        return False

def initialize_models():
    """Inicializar modelos de IA"""
    try:
        # Inicializar Gemini
        llm = GoogleGenerativeAI(
            model="gemini-2.5-flash",
            temperature=0,
            max_tokens=200
        )
        
        # Inicializar Whisper
        whisper_model = whisper.load_model("base")
        
        print("✅ Modelos inicializados correctamente")
        return llm, whisper_model
    except Exception as e:
        print(f"❌ Error inicializando modelos: {e}")
        raise

def process_video(youtube_url: str) -> Dict[str, Any]:
    """
    Procesar un video de YouTube y enviar resumen al webhook

    Args:
        youtube_url: URL de YouTube
    
    Returns:
        Dict con resultados del procesamiento
    """
    try:
        # Verificar dependencias
        if not check_dependencies():
            return {"error": "FFmpeg no disponible", "success": False}
        
        # Inicializar modelos
        llm, whisper_model = initialize_models()
        
        # Configurar text splitter
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=2000, chunk_overlap=200)
        
        # Configurar prompts
        map_prompt = PromptTemplate(
            input_variables=["text"],
            template="Resume el siguiente texto de manera concisa en español:\n\n{text}"
        )
        combine_prompt = PromptTemplate(
            input_variables=["text"],
            template="Resume los siguientes textos de manera concisa en español, combinando la información de forma coherente:\n\n{text}"
        )
        
        results = []

        try:
            print(f"🎥 Procesando: {youtube_url}")

            # Configurar yt-dlp
            ydl_opts = {
                    'format': 'bestaudio/best',  # Intenta el mejor audio disponible
                    'postprocessors': [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '192',
                    }],
                    'outtmpl': 'audio_%(id)s.%(ext)s',
                    'quiet': True,
                    'postprocessor_args': ['-y'],
                    'fragment_retries': 5,  # Reintenta descargar fragmentos hasta 5 veces
                    'retry_sleep': 5,  # Espera 5 segundos entre reintentos
                    'http_chunk_size': 1048576,  # Tamaño de chunk más pequeño para conexiones lentas
                    'socket_timeout': 30,  # Aumenta el timeout a 30 segundos
                }
                # Descargar audio
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(youtube_url, download=True)
                video_title = info.get('title', 'Unknown')
                video_id = info['id']
                audio_file = f"audio_{video_id}.mp3"
            
            # Transcribir con Whisper
            if os.path.exists(audio_file):
                print(f"🎙️ Transcribiendo {audio_file}...")
                result = whisper_model.transcribe(audio_file)
                transcript = result["text"]
                
                # Dividir texto en chunks
                texts = text_splitter.create_documents([transcript])
                
                # Generar resumen
                if texts:
                    chain = load_summarize_chain(
                        llm,
                        chain_type="map_reduce",
                        map_prompt=map_prompt,
                        combine_prompt=combine_prompt,
                        verbose=False
                    )
                    
                    summary_output = chain.invoke({"input_documents": texts})
                    summary = summary_output["output_text"]
                    
                    # Preparar datos para webhook
                    video_data = {
                        "url": youtube_url,
                        "title": video_title,
                        "video_id": video_id,
                        "summary": summary,
                        "transcript_length": len(transcript),
                        "chunks_processed": len(texts)
                    }
                    
                    # Enviar al webhook de n8n
                    webhook_response = send_to_webhook(video_data)
                    
                    results.append({
                        "url": youtube_url,
                        "title": video_title,
                        "summary": summary,
                        "webhook_status": webhook_response.get("status", "error"),
                        "success": True
                    })
                    
                    print(f"✅ Procesado: {video_title}")
                
                # Limpiar archivo temporal
                if os.path.exists(audio_file):
                    os.remove(audio_file)
                    
            else:
                results.append({
                    "url": youtube_url,
                    "error": "No se pudo descargar el audio",
                    "success": False
                })
                    
        except Exception as e:
            print(f"❌ Error procesando {youtube_url}: {e}")
            results.append({
                "url": youtube_url,
                "error": str(e),
                "success": False
            })
        
        return {
            "success": True,
            "processed_videos": len(results),
            "successful_videos": len([r for r in results if r.get("success", False)]),
            "results": results
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "results": []
        }

def process_youtube_video(url: str) -> Dict[str, Any]:
    print(f"🟢 Entrando a process_youtube_video con url: {url}")
    summary = process_video(url)
    # Lógica para enviar resúmenes al webhook (puedes usar requests.post)
    return summary

def send_to_webhook(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enviar datos al webhook de n8n
    
    Args:
        data: Datos a enviar
    
    Returns:
        Respuesta del webhook
    """
    webhook_url = "https://pardinian.app.n8n.cloud/webhook-test/09484a9c-bccb-4344-8f11-957aed42daef"
    try:
        response = requests.post(
            webhook_url,
            json=data,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        response.raise_for_status()
        
        return {
            "status": "success",
            "status_code": response.status_code,
            "response": response.json() if response.content else {}
        }
        
    except requests.exceptions.Timeout:
        return {"status": "timeout", "error": "Webhook timeout"}
    except requests.exceptions.RequestException as e:
        return {"status": "error", "error": str(e)}
    except Exception as e:
        return {"status": "error", "error": f"Unexpected error: {str(e)}"}

# Función de prueba
if __name__ == "__main__":
    test_urls = ["https://www.youtube.com/watch?v=nW-q3Xb8paU"]
    
    result = process_youtube_video(test_urls)
    print("Resultado:", result)