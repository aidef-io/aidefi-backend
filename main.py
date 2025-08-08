import os
from fastapi import FastAPI
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware

from modules.ai.controller import router as ai_router
from modules.rpc.controller import router as rpc_router
load_dotenv()



app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    # allow_origins=[FRONTEND_URL], 
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"], 
    allow_headers=["*"], 
)

app.include_router(ai_router, prefix="/ai", tags=["AI"])
app.include_router(rpc_router, prefix="/rpc", tags=["RPC"])

@app.get("/")
async def root():
    """Ana endpoint"""
    return {"message": "Welcome to the DeFi Transaction Assistant API"}

@app.get("/health")
async def health_check():
    """Sağlık kontrolü endpoint'i"""
    return {"status": "healthy", "service": "DeFi Transaction Assistant"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("APP_PORT", 8000)), reload=True)

