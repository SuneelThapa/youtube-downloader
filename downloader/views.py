import os
import uuid
import re
import yt_dlp
import threading
from django.conf import settings
from django.shortcuts import render
from django.http import FileResponse, HttpResponse, JsonResponse


# 📁 Download folder
DOWNLOAD_DIR = os.path.join(settings.BASE_DIR, 'downloads')
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# 🔧 PATHS
FFMPEG_PATH = r'C:\Users\emporium Armani\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1-full_build\bin'
NODE_PATH = r'C:\Program Files\nodejs\node.exe'

# 🧠 MEMORY STORE
DOWNLOAD_PROGRESS = {}
DOWNLOAD_FILES = {}
DOWNLOAD_META = {}

# =========================
# 🧹 ANSI CLEANER
# =========================
ANSI_ESCAPE = re.compile(r'\x1b\[[0-9;]*m')

def clean_text(value):
    if not value:
        return "--"
    return ANSI_ESCAPE.sub('', str(value)).strip()


# =========================
# 🔧 DEBUG (optional)
# =========================
def debug_progress(request, job_id):
    return JsonResponse({
        'progress': DOWNLOAD_PROGRESS.get(job_id, {}),
        'file_ready': job_id in DOWNLOAD_FILES,
    })


# =========================
# 🔧 HELPERS
# =========================
def clean_url(url):
    return url.split("&")[0] if url else ""


def get_ydl_opts_base(job_id=None):
    return {
        'ignoreconfig': True,
        'nocheckcertificate': True,
        'http_headers': {'User-Agent': 'Mozilla/5.0'},
        'source_address': '0.0.0.0',
        'socket_timeout': 10,
        'retries': 1,
        'quiet': True,
        'noplaylist': True,
        'ffmpeg_location': FFMPEG_PATH,
        'js_runtimes': {
            'node': {'path': NODE_PATH}
        },
        'progress_hooks': [
            lambda d: progress_hook(d, job_id) if job_id else None
        ],
    }


# =========================
# 📊 PROGRESS HOOK (FIXED)
# =========================
def progress_hook(d, job_id):
    if not job_id:
        return

    try:
        status = d.get('status')

        # =========================
        # DOWNLOADING
        # =========================
        if status == 'downloading':

            percent = clean_text(d.get('_percent_str', '0%'))
            speed = clean_text(d.get('_speed_str') or d.get('speed'))
            eta = clean_text(d.get('_eta_str') or d.get('eta'))

            DOWNLOAD_PROGRESS[job_id] = {
                'percent': percent,   # IMPORTANT: keep string like "45.3%"
                'speed': speed or "--",
                'eta': eta or "--",
                'status': 'downloading'
            }

        # =========================
        # FINISHED
        # =========================
        elif status == 'finished':
            DOWNLOAD_PROGRESS[job_id] = {
                'percent': "100%",
                'speed': "--",
                'eta': "--",
                'status': 'finished'
            }

    except Exception as e:
        DOWNLOAD_PROGRESS[job_id] = {
            'status': 'error',
            'error': str(e)
        }


# =========================
# 🚀 BACKGROUND DOWNLOAD
# =========================
def start_download(url, format_id, format_type):
    job_id = str(uuid.uuid4())

    def run():
        try:
            ydl_opts = get_ydl_opts_base(job_id)
            ydl_opts.update({
                'outtmpl': os.path.join(DOWNLOAD_DIR, '%(title)s.%(ext)s'),
            })

            if format_type == "mp3":
                ydl_opts.update({
                    'format': 'bestaudio/best',
                    'postprocessors': [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                    }]
                })
            else:
                ydl_opts.update({
                    'format': format_id,
                    'merge_output_format': 'mp4',
                })

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                file_path = ydl.prepare_filename(info)

            if format_type == "mp3":
                file_path = os.path.splitext(file_path)[0] + ".mp3"

            DOWNLOAD_FILES[job_id] = file_path

            DOWNLOAD_META[job_id] = {
                "title": info.get("title"),
                "filesize": info.get("filesize")
            }

        except Exception as e:
            DOWNLOAD_PROGRESS[job_id] = {
                'status': 'error',
                'error': str(e)
            }

    threading.Thread(target=run, daemon=True).start()

    return job_id


# =========================
# 🏠 HOME VIEW
# =========================
def home(request):
    video_info = None
    formats = []
    error = None

    if request.method == "POST":
        url = clean_url(request.POST.get("url"))

        # 🎬 DOWNLOAD
        if "download" in request.POST:
            job_id = start_download(
                url,
                request.POST.get("format_id"),
                request.POST.get("type")
            )

            return render(request, "downloader/progress.html", {
                "job_id": job_id
            })

        # 👀 PREVIEW
        try:
            ydl_opts = get_ydl_opts_base()
            ydl_opts.update({
                'skip_download': True,
                'simulate': True,
            })

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)

            video_info = {
                "title": info.get("title"),
                "thumbnail": info.get("thumbnail"),
                "duration": info.get("duration"),
            }

            seen = set()
            for f in info.get("formats", []):
                if f.get("ext") == "mp4" and f.get("height"):
                    h = f["height"]

                    if h >= 1080:
                        label = "1080p"
                    elif h >= 720:
                        label = "720p"
                    elif h >= 480:
                        label = "480p"
                    else:
                        continue

                    if label not in seen:
                        formats.append({
                            "format_id": f["format_id"],
                            "label": label
                        })
                        seen.add(label)

            formats = sorted(formats, key=lambda x: int(x["label"][:-1]), reverse=True)

        except Exception as e:
            error = str(e)

    return render(request, "downloader/home.html", {
        "video_info": video_info,
        "formats": formats,
        "error": error
    })


# =========================
# 📊 HTMX PROGRESS VIEW
# =========================
def progress_view(request, job_id):
    data = DOWNLOAD_PROGRESS.get(job_id, {
        "percent": "0%",
        "speed": "--",
        "eta": "--",
        "status": "starting"
    })

    file_ready = job_id in DOWNLOAD_FILES

    return render(request, "downloader/progress_partial.html", {
        "data": data,
        "job_id": job_id,
        "file_ready": file_ready
    })


# =========================
# 📥 DOWNLOAD FILE
# =========================
def download_file(request, job_id):
    file_path = DOWNLOAD_FILES.get(job_id)

    if not file_path or not os.path.exists(file_path):
        return HttpResponse("File not found")

    file_handle = open(file_path, "rb")
    response = FileResponse(file_handle, as_attachment=True)

    def cleanup():
        try:
            file_handle.close()
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            print("Cleanup error:", e)

    threading.Timer(5, cleanup).start()

    return response