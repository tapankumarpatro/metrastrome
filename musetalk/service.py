"""
MuseTalk Lip-Sync Microservice
Runs on port 8001 inside the 'musetalk' conda environment.

Endpoints:
  POST /prepare   — pre-process a face image for an agent (run once per agent)
  POST /generate  — audio bytes in, base64 video frames out
  GET  /health    — health check
"""

import os
import sys
import io
import time
import json
import copy
import glob
import pickle
import shutil
import base64
import tempfile
import logging
from pathlib import Path
from typing import Dict, Optional

import cv2
import numpy as np
import torch
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
import uvicorn

# ── Ensure the musetalk package is importable ──
MUSETALK_ROOT = Path(__file__).parent
sys.path.insert(0, str(MUSETALK_ROOT))

from musetalk.utils.utils import load_all_model, datagen
from musetalk.utils.preprocessing import get_landmark_and_bbox, read_imgs
from musetalk.utils.blending import get_image_prepare_material, get_image_blending
from musetalk.utils.face_parsing import FaceParsing
from musetalk.utils.audio_processor import AudioProcessor
from transformers import WhisperModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("musetalk-service")

# ── Config ──
DEVICE = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
MODEL_DIR = MUSETALK_ROOT / "models"
VERSION = "v15"  # Use MuseTalk 1.5 (better quality)
BATCH_SIZE = 8   # Lower batch size for 12GB VRAM
FPS = 25
EXTRA_MARGIN = 10
PARSING_MODE = "jaw"

app = FastAPI(title="MuseTalk Lip-Sync Service")

# ── Global model state ──
models_loaded = False
vae = None
unet = None
pe = None
timesteps = None
whisper_model = None
audio_processor = None
fp = None
weight_dtype = None

# Prepared avatars: agent_id -> dict of precomputed data
prepared_avatars: Dict[str, dict] = {}


def load_models():
    """Load all MuseTalk models to GPU."""
    global models_loaded, vae, unet, pe, timesteps
    global whisper_model, audio_processor, fp, weight_dtype

    if models_loaded:
        return

    logger.info("Loading MuseTalk models to %s ...", DEVICE)
    start = time.time()

    # Core models
    vae, unet, pe = load_all_model(
        unet_model_path=str(MODEL_DIR / "musetalkV15" / "unet.pth"),
        vae_type="sd-vae",
        unet_config=str(MODEL_DIR / "musetalkV15" / "musetalk.json"),
        device=DEVICE,
    )
    timesteps = torch.tensor([0], device=DEVICE)

    # Half precision for speed
    pe = pe.half().to(DEVICE)
    vae.vae = vae.vae.half().to(DEVICE)
    unet.model = unet.model.half().to(DEVICE)

    # Audio processing
    whisper_dir = str(MODEL_DIR / "whisper")
    audio_processor = AudioProcessor(feature_extractor_path=whisper_dir)
    weight_dtype = unet.model.dtype
    whisper_model = WhisperModel.from_pretrained(whisper_dir)
    whisper_model = whisper_model.to(device=DEVICE, dtype=weight_dtype).eval()
    whisper_model.requires_grad_(False)

    # Face parsing
    fp = FaceParsing(left_cheek_width=90, right_cheek_width=90)

    models_loaded = True
    logger.info("Models loaded in %.1fs, VRAM: %.1f MB",
                time.time() - start,
                torch.cuda.memory_allocated() / 1e6)


@app.on_event("startup")
async def startup():
    load_models()


@app.get("/health")
async def health():
    mem = torch.cuda.memory_allocated() / 1e6 if torch.cuda.is_available() else 0
    return {
        "status": "ok",
        "models_loaded": models_loaded,
        "device": str(DEVICE),
        "vram_used_mb": round(mem, 1),
        "prepared_avatars": list(prepared_avatars.keys()),
    }


class PrepareRequest(BaseModel):
    agent_id: str
    image_path: str  # absolute path to the face image


@app.post("/prepare")
async def prepare_avatar(req: PrepareRequest):
    """Pre-process a face image: detect face, extract landmarks, encode to VAE latents.
    This is done once per agent and cached in memory."""

    if req.agent_id in prepared_avatars:
        return {"status": "already_prepared", "agent_id": req.agent_id}

    if not os.path.exists(req.image_path):
        raise HTTPException(404, f"Image not found: {req.image_path}")

    logger.info("Preparing avatar for %s from %s", req.agent_id, req.image_path)
    start = time.time()

    try:
        # Read the image
        img = cv2.imread(req.image_path)
        if img is None:
            raise HTTPException(400, f"Failed to read image: {req.image_path}")

        # Save as temp file for landmark detection (expects a list of paths)
        temp_dir = tempfile.mkdtemp(prefix=f"musetalk_{req.agent_id}_")
        temp_img_path = os.path.join(temp_dir, "00000000.png")
        cv2.imwrite(temp_img_path, img)

        # Extract landmarks and bounding box
        coord_list, frame_list = get_landmark_and_bbox([temp_img_path], upperbondrange=0)

        if not coord_list or coord_list[0] == (0.0, 0.0, 0.0, 0.0):
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise HTTPException(400, "No face detected in image")

        # Encode face region to VAE latents
        input_latent_list = []
        for bbox, frame in zip(coord_list, frame_list):
            x1, y1, x2, y2 = bbox
            # Add extra margin for v1.5
            y2 = min(y2 + EXTRA_MARGIN, frame.shape[0])
            coord_list[0] = [x1, y1, x2, y2]
            crop_frame = frame[y1:y2, x1:x2]
            resized = cv2.resize(crop_frame, (256, 256), interpolation=cv2.INTER_LANCZOS4)
            latents = vae.get_latents_for_unet(resized)
            input_latent_list.append(latents)

        # Create cycle (forward + reverse for smooth looping)
        frame_list_cycle = frame_list + frame_list[::-1]
        coord_list_cycle = coord_list + coord_list[::-1]
        latent_list_cycle = input_latent_list + input_latent_list[::-1]

        # Generate masks for blending
        mask_list_cycle = []
        mask_coords_list_cycle = []
        for i, frame in enumerate(frame_list_cycle):
            x1, y1, x2, y2 = coord_list_cycle[i]
            mask, crop_box = get_image_prepare_material(
                frame, [x1, y1, x2, y2], fp=fp, mode=PARSING_MODE
            )
            mask_list_cycle.append(mask)
            mask_coords_list_cycle.append(crop_box)

        # Store in memory
        prepared_avatars[req.agent_id] = {
            "frame_list_cycle": frame_list_cycle,
            "coord_list_cycle": coord_list_cycle,
            "latent_list_cycle": latent_list_cycle,
            "mask_list_cycle": mask_list_cycle,
            "mask_coords_list_cycle": mask_coords_list_cycle,
        }

        # Cleanup temp
        shutil.rmtree(temp_dir, ignore_errors=True)

        elapsed = time.time() - start
        logger.info("Avatar %s prepared in %.1fs", req.agent_id, elapsed)
        return {"status": "prepared", "agent_id": req.agent_id, "time_s": round(elapsed, 1)}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to prepare avatar %s", req.agent_id)
        raise HTTPException(500, str(e))


@app.post("/generate")
async def generate_lipsync(
    agent_id: str = Form(...),
    audio: UploadFile = File(...),
):
    """Generate lip-synced video frames from audio.
    Returns a JSON with base64-encoded JPEG frames."""

    if agent_id not in prepared_avatars:
        raise HTTPException(400, f"Avatar {agent_id} not prepared. Call /prepare first.")

    avatar = prepared_avatars[agent_id]
    logger.info("Generating lip-sync for %s, audio: %s", agent_id, audio.filename)
    start = time.time()

    # Save audio to temp file (MuseTalk needs a file path)
    audio_bytes = await audio.read()
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        f.write(audio_bytes)
        audio_path = f.name

    try:
        # Extract audio features
        whisper_features, librosa_length = audio_processor.get_audio_feature(
            audio_path, weight_dtype=weight_dtype
        )
        whisper_chunks = audio_processor.get_whisper_chunk(
            whisper_features, DEVICE, weight_dtype, whisper_model,
            librosa_length, fps=FPS,
            audio_padding_length_left=2,
            audio_padding_length_right=2,
        )

        video_num = len(whisper_chunks)
        logger.info("Audio → %d frames at %d fps", video_num, FPS)

        # Generate frames batch by batch
        gen = datagen(whisper_chunks, avatar["latent_list_cycle"], batch_size=BATCH_SIZE)
        frames = []
        idx = 0

        with torch.no_grad():
            for whisper_batch, latent_batch in gen:
                audio_feat = pe(whisper_batch.to(DEVICE))
                latent_batch = latent_batch.to(device=DEVICE, dtype=unet.model.dtype)

                pred_latents = unet.model(
                    latent_batch, timesteps,
                    encoder_hidden_states=audio_feat
                ).sample
                pred_latents = pred_latents.to(device=DEVICE, dtype=vae.vae.dtype)
                recon = vae.decode_latents(pred_latents)

                for res_frame in recon:
                    if idx >= video_num:
                        break
                    # Blend with original face
                    bbox = avatar["coord_list_cycle"][idx % len(avatar["coord_list_cycle"])]
                    ori_frame = copy.deepcopy(
                        avatar["frame_list_cycle"][idx % len(avatar["frame_list_cycle"])]
                    )
                    x1, y1, x2, y2 = bbox
                    try:
                        res_frame = cv2.resize(
                            res_frame.astype(np.uint8), (x2 - x1, y2 - y1)
                        )
                    except Exception:
                        idx += 1
                        continue

                    mask = avatar["mask_list_cycle"][idx % len(avatar["mask_list_cycle"])]
                    mask_crop = avatar["mask_coords_list_cycle"][
                        idx % len(avatar["mask_coords_list_cycle"])
                    ]
                    combined = get_image_blending(ori_frame, res_frame, bbox, mask, mask_crop)

                    # Encode as JPEG for transport
                    _, buf = cv2.imencode(".jpg", combined, [cv2.IMWRITE_JPEG_QUALITY, 85])
                    frames.append(base64.b64encode(buf).decode("ascii"))
                    idx += 1

        elapsed = time.time() - start
        logger.info("Generated %d frames in %.1fs (%.1f fps)",
                    len(frames), elapsed, len(frames) / elapsed if elapsed > 0 else 0)

        return JSONResponse({
            "agent_id": agent_id,
            "fps": FPS,
            "frame_count": len(frames),
            "generation_time_s": round(elapsed, 2),
            "frames": frames,  # list of base64-encoded JPEGs
        })

    finally:
        os.unlink(audio_path)


@app.post("/generate_video")
async def generate_video(
    agent_id: str = Form(...),
    audio: UploadFile = File(...),
):
    """Generate lip-synced MP4 video from audio. Returns video bytes directly."""

    if agent_id not in prepared_avatars:
        raise HTTPException(400, f"Avatar {agent_id} not prepared. Call /prepare first.")

    avatar = prepared_avatars[agent_id]
    logger.info("Generating video for %s", agent_id)
    start = time.time()

    audio_bytes = await audio.read()
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        f.write(audio_bytes)
        audio_path = f.name

    output_path = tempfile.mktemp(suffix=".mp4")

    try:
        # Extract audio features
        whisper_features, librosa_length = audio_processor.get_audio_feature(
            audio_path, weight_dtype=weight_dtype
        )
        whisper_chunks = audio_processor.get_whisper_chunk(
            whisper_features, DEVICE, weight_dtype, whisper_model,
            librosa_length, fps=FPS,
            audio_padding_length_left=2,
            audio_padding_length_right=2,
        )

        video_num = len(whisper_chunks)

        # Generate all frames
        gen = datagen(whisper_chunks, avatar["latent_list_cycle"], batch_size=BATCH_SIZE)
        all_frames = []
        idx = 0

        with torch.no_grad():
            for whisper_batch, latent_batch in gen:
                audio_feat = pe(whisper_batch.to(DEVICE))
                latent_batch = latent_batch.to(device=DEVICE, dtype=unet.model.dtype)

                pred_latents = unet.model(
                    latent_batch, timesteps,
                    encoder_hidden_states=audio_feat
                ).sample
                pred_latents = pred_latents.to(device=DEVICE, dtype=vae.vae.dtype)
                recon = vae.decode_latents(pred_latents)

                for res_frame in recon:
                    if idx >= video_num:
                        break
                    bbox = avatar["coord_list_cycle"][idx % len(avatar["coord_list_cycle"])]
                    ori_frame = copy.deepcopy(
                        avatar["frame_list_cycle"][idx % len(avatar["frame_list_cycle"])]
                    )
                    x1, y1, x2, y2 = bbox
                    try:
                        res_frame = cv2.resize(
                            res_frame.astype(np.uint8), (x2 - x1, y2 - y1)
                        )
                    except Exception:
                        idx += 1
                        continue

                    mask = avatar["mask_list_cycle"][idx % len(avatar["mask_list_cycle"])]
                    mask_crop = avatar["mask_coords_list_cycle"][
                        idx % len(avatar["mask_coords_list_cycle"])
                    ]
                    combined = get_image_blending(ori_frame, res_frame, bbox, mask, mask_crop)
                    all_frames.append(combined)
                    idx += 1

        # Write frames to video using OpenCV
        if all_frames:
            h, w = all_frames[0].shape[:2]
            temp_video = tempfile.mktemp(suffix=".mp4")
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            writer = cv2.VideoWriter(temp_video, fourcc, FPS, (w, h))
            for frame in all_frames:
                writer.write(frame)
            writer.release()

            # Mux with audio using ffmpeg (yuv420p required for browser playback)
            import subprocess
            cmd = [
                "ffmpeg", "-y", "-v", "warning",
                "-i", temp_video,
                "-i", audio_path,
                "-c:v", "libx264", "-preset", "fast",
                "-crf", "23", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "128k",
                "-movflags", "+faststart",
                "-shortest",
                output_path,
            ]
            subprocess.run(cmd, check=True, capture_output=True)
            os.unlink(temp_video)

            with open(output_path, "rb") as f:
                video_bytes = f.read()

            elapsed = time.time() - start
            logger.info("Video generated: %d frames, %.1fs", len(all_frames), elapsed)

            return Response(
                content=video_bytes,
                media_type="video/mp4",
                headers={
                    "X-Frame-Count": str(len(all_frames)),
                    "X-Generation-Time": str(round(elapsed, 2)),
                },
            )
        else:
            raise HTTPException(500, "No frames generated")

    finally:
        for p in [audio_path, output_path]:
            if os.path.exists(p):
                os.unlink(p)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
