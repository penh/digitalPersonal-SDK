#!/usr/bin/env python3
"""
Example 4: REST API Microservice (FastAPI)
Exposes the DigitalPersona 4500 fingerprint reader as a local HTTP microservice
for integration with web frontends (React, Vue, Angular), mobile apps, or backend services.

Run with:
    pip install fastapi uvicorn
    python3 04_fastapi_rest_service.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from typing import List, Optional
from dp4500 import UareU4500, ReaderManager, FingerprintTemplate
from dp4500.backends.mock import MockBackend

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel
    import uvicorn
except ImportError:
    print("FastAPI or Uvicorn not installed. Install via: pip install fastapi uvicorn")
    sys.exit(0)

app = FastAPI(
    title="DigitalPersona 4500 Biometric API",
    description="REST API for fingerprint capture, enrollment, verification, and identification",
    version="1.0.0",
)

# Enable CORS for browser JavaScript requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global reader instance
READER_BACKEND = None
if "--mock" in sys.argv:
    READER_BACKEND = MockBackend()


class DeviceResponse(BaseModel):
    name: str
    driver: str
    device_id: str
    vendor_id: str
    product_id: str


class ScanResponse(BaseModel):
    width: int
    height: int
    dpi: int
    quality_score: int
    image_base64: str


class EnrollRequest(BaseModel):
    username: str
    finger_name: Optional[str] = "right_index"
    stages: Optional[int] = 5


class EnrollResponse(BaseModel):
    username: str
    finger_name: Optional[str]
    template_base64: str
    template_size: int


class VerifyRequest(BaseModel):
    template_base64: str


class VerifyResponse(BaseModel):
    matched: bool
    score: float


class Candidate(BaseModel):
    user_id: str
    template_base64: str


class IdentifyRequest(BaseModel):
    candidates: List[Candidate]


class IdentifyResponse(BaseModel):
    matched: bool
    user_id: Optional[str]
    score: float


@app.get("/health", response_model=List[DeviceResponse])
def get_status():
    """List connected fingerprint readers and their status."""
    devs = ReaderManager.list_readers()
    return [
        DeviceResponse(
            name=d.name,
            driver=d.driver,
            device_id=d.device_id,
            vendor_id=f"0x{d.vendor_id:04x}",
            product_id=f"0x{d.product_id:04x}",
        )
        for d in devs
    ]


@app.post("/scan", response_model=ScanResponse)
def scan_fingerprint():
    """Capture a live fingerprint image and return it as Base64 PNG."""
    try:
        with UareU4500(backend=READER_BACKEND) as reader:
            img = reader.capture(wait_for_finger=True)
            return ScanResponse(
                width=img.width,
                height=img.height,
                dpi=img.dpi,
                quality_score=img.quality_score,
                image_base64=f"data:image/png;base64,{img.to_base64(format='PNG')}",
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/enroll", response_model=EnrollResponse)
def enroll_fingerprint(req: EnrollRequest):
    """Perform multi-stage enrollment for a user."""
    try:
        with UareU4500(backend=READER_BACKEND) as reader:
            tpl = reader.enroll(
                stages=req.stages or 5,
                username=req.username,
                finger_name=req.finger_name,
            )
            return EnrollResponse(
                username=req.username,
                finger_name=req.finger_name,
                template_base64=tpl.to_base64(),
                template_size=tpl.size,
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/verify", response_model=VerifyResponse)
def verify_fingerprint(req: VerifyRequest):
    """Verify live finger on reader against a provided Base64 template."""
    try:
        tpl = FingerprintTemplate.from_base64(req.template_base64)
        with UareU4500(backend=READER_BACKEND) as reader:
            res = reader.verify(tpl)
            return VerifyResponse(matched=res.matched, score=res.score)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/identify", response_model=IdentifyResponse)
def identify_fingerprint(req: IdentifyRequest):
    """1:N match live finger against an array of candidate templates."""
    try:
        templates = []
        user_ids = []
        for cand in req.candidates:
            templates.append(FingerprintTemplate.from_base64(cand.template_base64))
            user_ids.append(cand.user_id)

        with UareU4500(backend=READER_BACKEND) as reader:
            res = reader.identify(templates)
            matched_user = user_ids[res.index] if res.matched and res.index is not None else None
            return IdentifyResponse(matched=res.matched, user_id=matched_user, score=res.score)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    print("Starting DigitalPersona 4500 REST API on http://127.0.0.1:8000 ...")
    uvicorn.run(app, host="127.0.0.1", port=8000)
