import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

router = APIRouter()

# Keep uploads stable even if the API starts from another working directory.
UPLOAD_DIR = Path(__file__).resolve().parent.parent / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _display_name(stored_name: str) -> str:
    parts = stored_name.split("_", 2)
    if len(parts) == 3:
        return parts[2]
    return stored_name


@router.post("/upload")
async def upload_files(
    files: list[UploadFile] = File(...),
    session_id: Optional[str] = Form(None),
    thread_id: Optional[str] = Form(None),
):
    uploaded_files = []

    for file in files:
        file_id = f"file_{uuid.uuid4().hex[:12]}_{file.filename}"
        file_path = UPLOAD_DIR / file_id

        try:
            with file_path.open("wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
        except Exception as exc:
            raise HTTPException(500, detail=f"Failed to save file {file.filename}: {exc}") from exc

        uploaded_files.append(
            {
                "id": file_id,
                "name": file.filename,
                "size": file_path.stat().st_size,
                "type": file.content_type,
                "uploaded_at": datetime.utcnow().isoformat(),
                "status": "uploaded",
                "session_id": session_id,
                "thread_id": thread_id,
            }
        )

    return {"object": "list", "data": uploaded_files}


@router.get("")
async def list_files(user_id: str = "default"):
    files = []

    if UPLOAD_DIR.exists():
        for file_path in UPLOAD_DIR.iterdir():
            if file_path.is_file():
                files.append(
                    {
                        "id": file_path.name,
                        "name": _display_name(file_path.name),
                        "size": file_path.stat().st_size,
                        "uploaded_at": datetime.fromtimestamp(file_path.stat().st_mtime).isoformat(),
                        "status": "uploaded",
                        "user_id": user_id,
                    }
                )

    return {"object": "list", "data": files}


@router.post("/save")
async def save_file(data: dict):
    filename = data.get("filename")
    content = data.get("content")
    path = data.get("path")

    if not filename or content is None:
        raise HTTPException(400, detail="filename and content are required")

    file_id = f"saved_{uuid.uuid4().hex[:12]}_{filename}"

    if path:
        save_path = Path(path) / filename
        save_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        save_path = UPLOAD_DIR / file_id

    try:
        with save_path.open("w", encoding="utf-8") as handle:
            handle.write(content)
    except Exception as exc:
        raise HTTPException(500, detail=f"Failed to save file: {exc}") from exc

    return {
        "object": "file",
        "id": file_id,
        "filename": filename,
        "path": str(save_path),
        "size": save_path.stat().st_size,
        "saved_at": datetime.utcnow().isoformat(),
    }


@router.delete("/{file_id}")
async def delete_file(file_id: str):
    file_path = UPLOAD_DIR / file_id

    if not file_path.exists():
        raise HTTPException(404, detail="File not found")

    try:
        file_path.unlink()
    except Exception as exc:
        raise HTTPException(500, detail=f"Failed to delete file: {exc}") from exc

    return {"object": "file", "deleted": True, "id": file_id}
