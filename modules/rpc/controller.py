from fastapi import APIRouter
from dotenv import load_dotenv
from modules.rpc.service import RPCService
from modules.rpc.dto.rpcDto import rpcDTO

load_dotenv()

router = APIRouter()



@router.post("/get-info")
async def get_info(rpc: rpcDTO):
    return RPCService.info(rpc)


@router.post("/test")
async def test_rpc():
    """Test RPC endpoint"""
    return {"message": "RPC endpoint is working!"}