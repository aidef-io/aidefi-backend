from fastapi import APIRouter
from dotenv import load_dotenv

load_dotenv()

router = APIRouter()



@router.post("/test")
async def test_rpc():
    """Test RPC endpoint"""
    return {"message": "RPC endpoint is working!"}