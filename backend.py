#!/usr/bin/env python3
"""
Refrakt Backend API Server - Simplified Version

This FastAPI server provides a single /run endpoint that:
1. Takes natural language prompts
2. Generates YAML configs via OpenAI
3. Runs refrakt training jobs
4. Manages job status and results

Usage:
    python backend.py [dev|prod]

The server will run on:
- dev: http://localhost:8001 (with hot reload)
- prod: http://localhost:8002
- default: http://localhost:8000
"""

import asyncio
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
from pydantic import BaseModel

# Load environment variables
load_dotenv()

# Configure OpenAI API
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")

if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY environment variable is required")

openai_client = OpenAI(api_key=OPENAI_API_KEY)

# Initialize FastAPI app
app = FastAPI(
    title="Refrakt Backend API",
    description="Backend API for Refrakt ML Framework",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory job storage
jobs = {}

# Pydantic models
class JobRequest(BaseModel):
    prompt: str
    user_id: Optional[str] = "anonymous"

class JobResponse(BaseModel):
    job_id: str
    status: str
    message: str

class JobStatus(BaseModel):
    job_id: str
    status: str
    created_at: str
    updated_at: str
    config: Optional[dict] = None
    result_path: Optional[str] = None
    error: Optional[str] = None

def load_prompt_template():
    """Load the prompt template from PROMPT.md"""
    prompt_path = Path("PROMPT.md")
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt template not found at {prompt_path}")
    
    with open(prompt_path, 'r', encoding='utf-8') as f:
        return f.read()

PROMPT_TEMPLATE = load_prompt_template()

@app.get("/")
async def root():
    """Root endpoint - API information"""
    return {
        "message": "Refrakt Backend API",
        "version": "1.0.0",
        "docs": "/docs",
        "endpoints": {
            "run_job": "/run",
            "job_status": "/job/{job_id}",
            "jobs_list": "/jobs",
            "download_result": "/download/{job_id}",
            "test_openai": "/test-openai"
        }
    }

@app.get("/test-openai")
async def test_openai():
    """Test OpenAI API connection"""
    try:
        response = openai_client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "user", "content": "Hello, respond with 'API connection successful'"}
            ],
            max_tokens=50
        )
        return {
            "status": "success",
            "response": response.choices[0].message.content,
            "model": OPENAI_MODEL,
            "api_key_configured": True
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "api_key_configured": False
        }

@app.post("/run", response_model=JobResponse)
async def run_job(request: JobRequest):
    """Run complete pipeline: prompt → YAML → training"""
    job_id = str(uuid.uuid4())
    
    try:
        # Initialize job status
        jobs[job_id] = {
            "job_id": job_id,
            "status": "generating",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "prompt": request.prompt,
            "user_id": request.user_id
        }
        
        # Generate YAML using OpenAI
        try:
            messages = [
                {"role": "system", "content": PROMPT_TEMPLATE},
                {"role": "user", "content": f"USER_REQUEST: {request.prompt}\n---\nYAML:"}
            ]
            
            print(f"DEBUG: Sending prompt to OpenAI (model: {OPENAI_MODEL}, length: {len(PROMPT_TEMPLATE) + len(request.prompt)})")
            response = openai_client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=messages,
                temperature=0.3,  # Lower temperature for more consistent YAML generation
                max_tokens=4000
            )
            
            yaml_text = response.choices[0].message.content
            print(f"DEBUG: Raw OpenAI response (length: {len(yaml_text)})")
            
            # Clean the YAML text (remove markdown code blocks if present)
            yaml_text = yaml_text.strip("` \n")
            
            # Remove common prefixes that LLMs might add
            if yaml_text.startswith("yaml\n"):
                yaml_text = yaml_text[5:]
            elif yaml_text.startswith("```yaml\n"):
                yaml_text = yaml_text[8:]
            elif yaml_text.startswith("```\n"):
                yaml_text = yaml_text[4:]
            
            # Remove trailing backticks
            if yaml_text.endswith("```"):
                yaml_text = yaml_text[:-3]
            
            yaml_text = yaml_text.strip()
            print(f"DEBUG: Cleaned YAML text (length: {len(yaml_text)})")
            
        except Exception as e:
            print(f"DEBUG: OpenAI API error: {str(e)}")
            raise HTTPException(status_code=500, detail=f"OpenAI API error: {str(e)}")
        
        # Validate YAML
        try:
            print(f"DEBUG: Attempting to parse YAML...")
            config = yaml.safe_load(yaml_text)
            print(f"DEBUG: YAML parsed successfully!")
            print(f"DEBUG: Config keys: {list(config.keys()) if config else 'None'}")
            
            jobs[job_id]["config"] = config
            jobs[job_id]["status"] = "running"
            jobs[job_id]["updated_at"] = datetime.now().isoformat()
            
        except yaml.YAMLError as e:
            print(f"DEBUG: YAML parsing error: {str(e)}")
            jobs[job_id]["status"] = "error"
            jobs[job_id]["error"] = f"Invalid YAML generated: {str(e)}"
            jobs[job_id]["updated_at"] = datetime.now().isoformat()
            raise HTTPException(status_code=400, detail=f"Invalid YAML generated: {str(e)}")
        
        # Save config to temporary file and start training
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_text)
            config_path = f.name
        
        # Start training in background
        asyncio.create_task(run_refrakt_job(job_id, config_path))
        
        return JobResponse(
            job_id=job_id,
            status="running",
            message="Job started successfully"
        )
        
    except Exception as e:
        if job_id in jobs:
            jobs[job_id]["status"] = "error"
            jobs[job_id]["error"] = str(e)
            jobs[job_id]["updated_at"] = datetime.now().isoformat()
        raise HTTPException(status_code=500, detail=f"Error running job: {str(e)}")

async def read_stream_chunks(stream, chunk_size: int = 8192):
    """
    Read from stream in chunks, handling both newline and carriage return sequences.
    This function handles tqdm progress bars that use \r for line updates.
    
    Args:
        stream: Async stream to read from
        chunk_size: Size of chunks to read
    
    Yields:
        Decoded text lines or chunks
    """
    buffer = b""
    
    while True:
        try:
            chunk = await stream.read(chunk_size)
            if not chunk:
                # Process remaining buffer before breaking
                if buffer:
                    # Try to decode and yield any remaining data
                    try:
                        remaining = buffer.decode('utf-8', errors='replace').rstrip()
                        if remaining:
                            yield remaining
                    except Exception:
                        pass
                break
            
            buffer += chunk
            
            # Process buffer looking for line separators
            # Handle both \n (newline) and \r (carriage return) sequences
            # Continue processing until no more separators are found
            processed = True
            while processed:
                processed = False
                
                # Check for newline first (standard line separator)
                # This handles both \n and \r\n sequences
                if b'\n' in buffer:
                    line_bytes, buffer = buffer.split(b'\n', 1)
                    try:
                        # Strip any trailing \r from \r\n sequences
                        line_text = line_bytes.decode('utf-8', errors='replace').rstrip('\r').strip()
                        if line_text:  # Only yield non-empty lines
                            yield line_text
                    except Exception as e:
                        # If decoding fails, skip this chunk
                        print(f"DEBUG: Decode error: {e}")
                    processed = True
                    continue
                
                # Check for carriage return (tqdm uses this for progress bars)
                # When we see \r without \n, we treat it as a line separator too
                if b'\r' in buffer:
                    # Extract up to the \r, but keep processing
                    parts = buffer.split(b'\r', 1)
                    if len(parts) == 2:
                        line_bytes, buffer = parts
                        try:
                            line_text = line_bytes.decode('utf-8', errors='replace').strip()
                            if line_text:  # Only yield non-empty lines
                                yield line_text
                        except Exception:
                            pass
                        processed = True
                        continue
                
                # If buffer is getting too large without separators, flush a chunk
                # This prevents "chunk exceed the limit" errors
                if len(buffer) > chunk_size * 4:
                    # Extract a chunk to prevent buffer overflow
                    chunk_to_process = buffer[:chunk_size * 2]
                    buffer = buffer[chunk_size * 2:]
                    try:
                        chunk_text = chunk_to_process.decode('utf-8', errors='replace').rstrip()
                        if chunk_text:
                            yield chunk_text
                    except Exception:
                        pass
                    processed = True
                    continue
                
                # No separator found and buffer is reasonable size, wait for more data
                break
                    
        except Exception as e:
            print(f"DEBUG: Stream read error: {e}")
            break


def extract_model_name(config: dict) -> Optional[str]:
    """
    Extract model_name from config, handling autoencoder variants.
    
    Args:
        config: Configuration dictionary
    
    Returns:
        Model name or None if not found
    """
    if not config or "model" not in config:
        return None
    
    model_name = config["model"].get("name", None)
    # Handle autoencoder variant naming
    if model_name == "autoencoder" and "params" in config["model"]:
        variant = config["model"]["params"].get("variant", "simple")
        model_name = f"autoencoder_{variant}"
    
    return model_name


def extract_experiment_id(output_lines: list[str]) -> Optional[str]:
    """
    Extract experiment_id from log output.
    
    Args:
        output_lines: List of log output lines
    
    Returns:
        Experiment ID (YYYYMMDD_HHMMSS) or None if not found
    """
    # Pattern: "🔬 Experiment ID: 20251105_174807" or "Experiment ID: 20251105_174807"
    for line in output_lines:
        if "Experiment ID:" in line:
            # Extract the experiment_id using regex
            # Match pattern: "Experiment ID: YYYYMMDD_HHMMSS"
            match = re.search(r'Experiment ID:\s*(\d{8}_\d{6})', line)
            if match:
                experiment_id = match.group(1)
                print(f"DEBUG: Extracted experiment_id: {experiment_id}")
                return experiment_id
    return None


def consolidate_log_files(job_id: str, model_name: Optional[str]) -> bool:
    """
    Move log files from jobs/{job_id}/{model_name}/ to jobs/{job_id}/ and remove empty model_name directory.
    
    Args:
        job_id: Job ID
        model_name: Model name (used to find the log subdirectory)
    
    Returns:
        True if logs were moved successfully, False otherwise
    """
    if not model_name:
        return False
    
    job_dir = f"./jobs/{job_id}"
    log_subdir = os.path.join(job_dir, model_name)
    
    if not os.path.exists(log_subdir):
        return False
    
    try:
        # Move all log files from subdirectory to job directory
        for item in os.listdir(log_subdir):
            src = os.path.join(log_subdir, item)
            dst = os.path.join(job_dir, item)
            
            if os.path.isfile(src):
                # Move log file to top level
                if os.path.exists(dst):
                    # If file already exists, append content or rename
                    dst = os.path.join(job_dir, f"{model_name}_{item}")
                shutil.move(src, dst)
                print(f"DEBUG: Moved log file {item} to job directory")
        
        # Remove now-empty model_name directory
        try:
            os.rmdir(log_subdir)
            print(f"DEBUG: Removed empty {model_name} subdirectory")
        except OSError:
            # Directory not empty, that's okay
            print(f"DEBUG: Could not remove {model_name} subdirectory (not empty)")
        
        return True
        
    except Exception as e:
        print(f"DEBUG: Error consolidating log files: {e}")
        return False


def copy_checkpoint_files_to_job_dir(
    job_id: str, 
    experiment_id: Optional[str], 
    model_name: Optional[str],
    config_path: str
) -> bool:
    """
    Copy all checkpoint files from checkpoints directory to job directory.
    
    Args:
        job_id: Job ID
        experiment_id: Experiment ID (timestamp format: YYYYMMDD_HHMMSS)
        model_name: Model name (e.g., "resnet18")
        config_path: Path to the YAML config file used for training
    
    Returns:
        True if files were copied successfully, False otherwise
    """
    if not experiment_id or not model_name:
        print(f"DEBUG: Cannot copy checkpoint files - missing experiment_id or model_name")
        print(f"DEBUG: experiment_id={experiment_id}, model_name={model_name}")
        return False
    
    # Construct checkpoint directory path
    checkpoint_dir = os.path.join("./checkpoints", f"{model_name}_{experiment_id}")
    job_dir = f"./jobs/{job_id}"
    
    if not os.path.exists(checkpoint_dir):
        print(f"DEBUG: Checkpoint directory not found: {checkpoint_dir}")
        return False
    
    try:
        # Copy all contents from checkpoint directory to job directory
        # This includes: weights/, explanations/, *.yaml, *.joblib, etc.
        for item in os.listdir(checkpoint_dir):
            src = os.path.join(checkpoint_dir, item)
            dst = os.path.join(job_dir, item)
            
            if os.path.isdir(src):
                # Copy directory recursively
                if os.path.exists(dst):
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
                print(f"DEBUG: Copied directory {item} to job directory")
            else:
                # Copy file
                shutil.copy2(src, dst)
                print(f"DEBUG: Copied file {item} to job directory")
        
        # Also copy the config YAML file that was used for training
        if os.path.exists(config_path):
            config_dst = os.path.join(job_dir, os.path.basename(config_path))
            # Also save with a more descriptive name
            config_dst_named = os.path.join(job_dir, f"{model_name}.yaml")
            shutil.copy2(config_path, config_dst)
            shutil.copy2(config_path, config_dst_named)
            print(f"DEBUG: Copied config file to job directory")
        
        print(f"DEBUG: Successfully copied all checkpoint files from {checkpoint_dir} to {job_dir}")
        return True
        
    except Exception as e:
        print(f"DEBUG: Error copying checkpoint files: {e}")
        return False


async def run_refrakt_job(job_id: str, config_path: str):
    """Run refrakt CLI job in background"""
    try:
        # Create output directory
        output_dir = f"./jobs/{job_id}"
        os.makedirs(output_dir, exist_ok=True)
        
        # Get config from jobs dict if available, otherwise load from file
        # This avoids duplication - config is already parsed and stored in run_job
        config = jobs[job_id].get("config")
        if not config:
            # Fallback: load from file if not in jobs dict
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
        
        # Extract model_name once (DRY principle)
        model_name = extract_model_name(config)
        if model_name:
            print(f"DEBUG: Extracted model_name: {model_name}")
        
        # Run refrakt CLI
        cmd = [
            "refrakt",
            "--config", config_path,
            "--log-dir", output_dir
        ]
        
        print(f"DEBUG: Running command: {' '.join(cmd)}")
        
        # Prepare environment variables for tqdm
        # When stdout is piped, tqdm should automatically detect non-TTY
        # and use newlines instead of carriage returns. We set these to help.
        env = os.environ.copy()
        # Set TERM to indicate we're not in a full terminal, but still allow tqdm to work
        # This helps tqdm choose appropriate output format
        if 'TERM' not in env:
            env['TERM'] = 'xterm-256color'
        # Force tqdm to use newlines when not in TTY (it should auto-detect, but this helps)
        env['TQDM_DISABLE'] = '0'  # Keep tqdm enabled, but let it auto-format
        
        # Run the command with real-time output streaming
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,  # Merge stderr into stdout
            cwd=os.getcwd(),
            env=env
        )
        
        # Stream output in real-time using chunked reading
        # This handles both \n and \r sequences from tqdm progress bars
        output_lines = []
        if process.stdout:
            try:
                async for line_text in read_stream_chunks(process.stdout):
                    if line_text:
                        output_lines.append(line_text)
                        print(f"[JOB {job_id}] {line_text}")
            except Exception as e:
                print(f"DEBUG: Error reading stream: {e}")
        
        # Wait for process to complete
        await process.wait()
        
        # Update job status
        if process.returncode == 0:
            # Extract experiment_id from logs (model_name already extracted from config)
            experiment_id = extract_experiment_id(output_lines)
            
            # Copy checkpoint files to job directory
            if experiment_id and model_name:
                copy_success = copy_checkpoint_files_to_job_dir(
                    job_id, experiment_id, model_name, config_path
                )
                if copy_success:
                    print(f"DEBUG: Checkpoint files copied to job directory")
                else:
                    print(f"DEBUG: Warning: Failed to copy checkpoint files to job directory")
                
                # Consolidate log files: move from jobs/{job_id}/{model_name}/ to jobs/{job_id}/
                consolidate_log_files(job_id, model_name)
            else:
                print(f"DEBUG: Warning: Could not extract experiment_id or model_name")
                print(f"DEBUG: experiment_id={experiment_id}, model_name={model_name}")
            
            jobs[job_id]["status"] = "completed"
            jobs[job_id]["result_path"] = output_dir
            print(f"DEBUG: Job {job_id} completed successfully")
        else:
            jobs[job_id]["status"] = "error"
            error_msg = "\n".join(output_lines[-10:]) if output_lines else "Unknown error"  # Last 10 lines as error
            jobs[job_id]["error"] = error_msg
            print(f"DEBUG: Job {job_id} failed with return code {process.returncode}")
            print(f"DEBUG: Job {job_id} error output: {error_msg}")
        
        jobs[job_id]["updated_at"] = datetime.now().isoformat()
        
    except Exception as e:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = str(e)
        jobs[job_id]["updated_at"] = datetime.now().isoformat()
        print(f"DEBUG: Job {job_id} failed with exception: {str(e)}")

@app.get("/job/{job_id}", response_model=JobStatus)
async def get_job_status(job_id: str):
    """Get job status by ID"""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job_data = jobs[job_id]
    print(f"DEBUG: Getting status for job {job_id}: {job_data}")
    
    try:
        return JobStatus(**job_data)
    except Exception as e:
        print(f"DEBUG: Error creating JobStatus for job {job_id}: {str(e)}")
        print(f"DEBUG: Job data keys: {list(job_data.keys())}")
        raise HTTPException(status_code=500, detail=f"Error creating job status: {str(e)}")

@app.get("/jobs")
async def list_jobs():
    """List all jobs"""
    return {"jobs": list(jobs.values())}

@app.get("/download/{job_id}")
async def download_result(job_id: str):
    """Download job results (placeholder)"""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs[job_id]
    if job["status"] != "completed":
        raise HTTPException(status_code=400, detail="Job not completed")
    
    return {"message": f"Download results for job {job_id}", "path": job.get("result_path")}

if __name__ == "__main__":
    import uvicorn
    import sys
    
    # Determine port and reload settings based on environment
    if len(sys.argv) > 1:
        env = sys.argv[1]
        if env == "dev":
            port = 8001
            reload = True  # Enable hot reload for dev
            print(f"🚀 Starting Refrakt Backend in DEVELOPMENT mode on port {port}")
            print(f"📡 Access via: http://localhost:{port}")
            print(f"🌐 Domain access: http://dev.akshath.tech (after port forwarding)")
            print(f"🔥 Hot reload enabled for development")
        elif env == "prod":
            port = 8002
            reload = False
            print(f"🚀 Starting Refrakt Backend in PRODUCTION mode on port {port}")
            print(f"📡 Access via: http://localhost:{port}")
            print(f"🌐 Domain access: http://refrakt.akshath.tech (after port forwarding)")
        else:
            port = 8000
            reload = False
            print(f"🚀 Starting Refrakt Backend in DEFAULT mode on port {port}")
    else:
        port = 8000
        reload = False
        print(f"🚀 Starting Refrakt Backend in DEFAULT mode on port {port}")
        print(f"💡 Usage: python backend.py [dev|prod]")
    
    if reload:
        # For hot reload, we need to use the import string
        uvicorn.run("backend:app", host="0.0.0.0", port=port, reload=True)
    else:
        # For production, we can use the app object directly
        uvicorn.run(app, host="0.0.0.0", port=port)
