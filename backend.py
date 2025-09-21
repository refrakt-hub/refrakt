#!/usr/bin/env python3
"""
Refrakt Backend API Server - Simplified Version

This FastAPI server provides a single /run endpoint that:
1. Takes natural language prompts
2. Generates YAML configs via Gemini
3. Runs refrakt training jobs
4. Manages job status and results

Usage:
    python backend_clean.py [dev|prod]

The server will run on:
- dev: http://localhost:8001 (with hot reload)
- prod: http://localhost:8002
- default: http://localhost:8000
"""

import asyncio
import os
import subprocess
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import google.generativeai as genai
import yaml
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Load environment variables
load_dotenv()

# Configure Gemini API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY environment variable is required")
genai.configure(api_key=GEMINI_API_KEY)

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
            "test_gemini": "/test-gemini"
        }
    }

@app.get("/test-gemini")
async def test_gemini():
    """Test Gemini API connection"""
    try:
        model = genai.GenerativeModel("gemini-2.5-pro")
        response = model.generate_content("Hello")
        return {
            "status": "success",
            "response": response.text,
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
        
        # Generate YAML using Gemini
        try:
            model = genai.GenerativeModel("gemini-2.5-pro")
            prompt = f"{PROMPT_TEMPLATE}\n\nUSER_REQUEST: {request.prompt}\n---\nYAML:"
            
            print(f"DEBUG: Sending prompt to Gemini (length: {len(prompt)})")
            completion = model.generate_content(prompt)
            print(f"DEBUG: Raw Gemini response: {repr(completion.text)}")
            
            # Clean the YAML text
            yaml_text = completion.text.strip("` \n")
            
            # Remove common prefixes that Gemini might add
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
            print(f"DEBUG: Gemini API error: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Gemini API error: {str(e)}")
        
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

async def run_refrakt_job(job_id: str, config_path: str):
    """Run refrakt CLI job in background"""
    try:
        # Create output directory
        output_dir = f"./jobs/{job_id}"
        os.makedirs(output_dir, exist_ok=True)
        
        # Run refrakt CLI
        cmd = [
            "refrakt",
            "--config", config_path,
            "--log-dir", output_dir
        ]
        
        print(f"DEBUG: Running command: {' '.join(cmd)}")
        
        # Run the command with real-time output streaming
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,  # Merge stderr into stdout
            cwd=os.getcwd()
        )
        
        # Stream output in real-time to show tqdm progress bar
        output_lines = []
        if process.stdout:
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                
                # Decode and print the line in real-time
                line_text = line.decode().rstrip()
                output_lines.append(line_text)
                print(f"[JOB {job_id}] {line_text}")
        
        # Wait for process to complete
        await process.wait()
        
        # Update job status
        if process.returncode == 0:
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
