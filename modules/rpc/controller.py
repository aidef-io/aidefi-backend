from fastapi import APIRouter
from dotenv import load_dotenv
from modules.rpc.service import RPCService
from modules.rpc.dto.rpcDto import rpcDTO
from modules.rpc.dto.priceDto import PriceDto

load_dotenv()

router = APIRouter()



@router.post("/get-info")
async def get_info(rpc: rpcDTO):
    return RPCService.info(rpc)

@router.post("/price")
async def price(price: PriceDto):

    return RPCService.price(price)