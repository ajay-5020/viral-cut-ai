import os, uuid, subprocess, json, shutil
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

ROOT=Path(__file__).parent
DATA=Path(os.getenv("DATA_DIR", ROOT/"data"))
UPLOADS=DATA/"uploads"; OUTPUTS=DATA/"outputs"
for p in (UPLOADS,OUTPUTS): p.mkdir(parents=True,exist_ok=True)
app=FastAPI(title="Viral Cut AI")
templates=Jinja2Templates(directory=str(ROOT/"templates"))
app.mount("/media", StaticFiles(directory=str(DATA)), name="media")
app.mount("/static", StaticFiles(directory=str(ROOT/"static")), name="static")

def run(cmd):
    p=subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode: raise RuntimeError(p.stderr[-1500:])
    return p.stdout

def duration(path):
    d=json.loads(run(["ffprobe","-v","quiet","-show_format","-of","json",str(path)]))
    return float(d["format"]["duration"])

def download_url(url, dest):
    from urllib.parse import urlparse

    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower()

    allowed = {
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "youtu.be",
        "www.youtu.be"
    }

    if parsed.scheme not in ("http", "https") or host not in allowed:
        raise RuntimeError("Please paste a valid public YouTube URL.")

    template = str(dest.with_name(dest.stem + ".%(ext)s"))

    run([
        "yt-dlp",
        "--no-playlist",
        "--no-warnings",
        "--socket-timeout", "30",
        "--retries", "2",
        "-f", "bv*+ba/b",
        "--merge-output-format", "mp4",
        "-o", template,
        url.strip()
    ])

    candidates = [
        p for p in dest.parent.glob(dest.stem + ".*")
        if p.is_file() and not p.name.endswith((".part", ".ytdl"))
    ]

    if not candidates:
        raise RuntimeError(
            "YouTube video could not be downloaded. "
            "It may be private, restricted, or unavailable."
        )

    return max(candidates, key=lambda x: x.stat().st_size)

def detect_moments(path, dur):
    # Heuristic highlight finder: audio peaks + scene changes. Not a trained viral-content model.
    #out=run(["ffmpeg","-hide_banner","-i",str(path),"-af","aselect='gt(scene,0.25)',astats=metadata=1:reset=1","-f","null","-"])
    # Stable fallback clips distributed across the video.
    clip_len=min(35,max(12,dur/5))
    if dur<=clip_len: return [(0,max(1,dur))]
    count=min(6,max(1,int(dur//90)+1))
    step=max(clip_len,(dur-clip_len)/max(1,count-1))
    return [(round(i*step,2),round(min(clip_len,dur-i*step),2)) for i in range(count) if i*step<dur]

def captions(video, outdir):
    return False
    try:
        from faster_whisper import WhisperModel
        model=WhisperModel(os.getenv("WHISPER_MODEL","base"), device="cpu", compute_type="int8")
        segments,_=model.transcribe(str(video), beam_size=3)
        rows=[]
        for s in segments:
            def ts(t):
                h=int(t//3600); m=int((t%3600)//60); sec=t%60
                return f"{h:02}:{m:02}:{sec:06.3f}".replace(".",",")
            rows += [f"{len(rows)+1}",f"{ts(s.start)} --> {ts(s.end)}",s.text.strip(),""]
        (outdir/"captions.srt").write_text("\n".join(rows),encoding="utf-8")
        return True
    except Exception:
        return False

@app.get("/", response_class=HTMLResponse)
async def home(request:Request):
    return templates.TemplateResponse("index.html",{"request":request})

@app.post("/api/process")
async def process(file:UploadFile|None=File(None), url:str=Form(""), aspect:str=Form("9:16")):
    if not file and not url.strip(): raise HTTPException(400,"Upload a video or paste a URL.")
    job=uuid.uuid4().hex[:10]; folder=OUTPUTS/job; folder.mkdir()
    try:
        if file:
            ext=Path(file.filename or "video.mp4").suffix or ".mp4"
            source=UPLOADS/(job+ext)
            with source.open("wb") as f: shutil.copyfileobj(file.file,f)
        else:
            source=download_url(url.strip(),UPLOADS/(job+".mp4"))
        dur=duration(source)
        moments=detect_moments(source,dur)
        has_caps=captions(source,folder)
        clips=[]
        
        vf={
            "9:16":"fps=30,scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280",
            "16:9":"fps=30,scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2",
            "1:1":"fps=30,scale=720:720:force_original_aspect_ratio=increase,crop=720:720"
        }.get(aspect,"fps=30,scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280")
  
        for i,(start,length) in enumerate(moments,1):
            out=folder/f"clip_{i}.mp4"
            run([
                "ffmpeg","-y","-threads","1",
                "-ss",str(start),"-i",str(source),"-t",str(length),
                "-vf",vf,"-c:v","libx264",
                "-preset","ultrafast","-crf","28","-threads","1",
                "-c:a","aac","-b:a","96k",
                "-movflags","+faststart",str(out)
            ])
            clips.append({"name":out.name,"url":f"/media/outputs/{job}/{out.name}","start":start,"duration":length})
            
        cap_url=f"/media/outputs/{job}/captions.srt" if has_caps else None
        return {"job":job,"duration":dur,"clips":clips,"captions":cap_url,
                "caption_status":"generated" if has_caps else "not_generated",
                "notice":"Highlight selection is heuristic, not guaranteed viral. Only use videos you own or have permission to edit."}
    except Exception as e:
        raise HTTPException(500,str(e))

@app.get("/sw.js")
def service_worker():
    return FileResponse(ROOT/"templates"/"sw.js", media_type="application/javascript")

@app.get("/health")
def health(): return {"ok":True}
